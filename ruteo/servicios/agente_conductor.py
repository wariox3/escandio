"""Agente de conductores (piloto, solo texto).

Le pregunta al conductor por su viaje y registra las NOVEDADES de las guias que
no se pudieron entregar. Las entregas OK no se tocan (esas requieren evidencia
foto/firma que por texto no hay).

El agente es un loop de tool-use sobre un cliente LLM agnostico. Las tools
REUSAN la logica de ruteo (no la reimplementan):
    - guias_pendientes : que guias faltan por resolver -> que preguntar.
    - tipos_novedad    : catalogo para mapear el motivo del conductor.
    - registrar_novedad: escribe la novedad (idempotente por movil_token).

El agente esta ACOTADO a un despacho: la tool nunca recibe despacho_id del
modelo, lo inyecta el contexto -> el LLM no puede tocar otro viaje.
"""
import logging

from django.utils import timezone

from movil.services.novedad import registrar_novedad
from ruteo.models.novedad_tipo import RutNovedadTipo
from ruteo.models.visita import RutVisita
from utilidades.llm import crear_cliente

logger = logging.getLogger(__name__)

MAX_RONDAS_TOOLS = 6      # tope de rondas de tool-use por mensaje (anti-loop)
MAX_GUIAS_LISTA = 60      # tope de guias que enumeramos al modelo

SYSTEM = """\
Sos un asistente de {empresa} que le escribe por WhatsApp al conductor {conductor} \
para cerrar el viaje #{despacho}. Hablás español colombiano, breve y claro.

Tu único objetivo: registrar las NOVEDADES de las guías que NO se pudieron entregar.
Las guías entregadas bien NO las toques (no las marcás de ninguna forma).

Reglas:
- Usá la tool `guias_pendientes` para saber qué guías faltan. Preguntá solo por esas.
- Referí SIEMPRE al número de guía exacto de esa lista. NUNCA inventes un número.
- Cuando el conductor diga que una guía tuvo problema, mapeá el motivo a un tipo con \
`tipos_novedad` y registrala con `registrar_novedad`. Si el motivo no encaja claro en \
un tipo, o no sabés a qué guía se refiere, PREGUNTÁ antes de registrar.
- No registres nada que el conductor no haya confirmado.
- Al terminar, resumí en una línea qué novedades quedaron registradas.
- Un mensaje corto por vez. No inventes datos que no tengas."""


class AgenteConductor:
    def __init__(self, despacho_id, tenant, cliente_llm=None, empresa='la empresa', conductor='conductor'):
        self.despacho_id = despacho_id
        self.tenant = tenant
        self.empresa = empresa
        self.conductor = conductor
        self.llm = cliente_llm or crear_cliente()
        self.novedades_registradas = []

    HERRAMIENTAS = [
        {
            'nombre': 'guias_pendientes',
            'descripcion': 'Lista las guías del viaje que todavía no están resueltas (ni entregadas ni con novedad). Es lo que hay que preguntarle al conductor.',
            'parametros': {'type': 'object', 'properties': {}},
        },
        {
            'nombre': 'tipos_novedad',
            'descripcion': 'Lista los tipos de novedad válidos (id + nombre) para clasificar el problema que reporte el conductor.',
            'parametros': {'type': 'object', 'properties': {}},
        },
        {
            'nombre': 'registrar_novedad',
            'descripcion': 'Registra una novedad para una guía que no se pudo entregar. Solo con una guía de guias_pendientes y un tipo de tipos_novedad.',
            'parametros': {
                'type': 'object',
                'properties': {
                    'guia_numero': {'type': 'string', 'description': 'Número exacto de la guía (de guias_pendientes).'},
                    'novedad_tipo_id': {'type': 'integer', 'description': 'id del tipo (de tipos_novedad).'},
                    'motivo': {'type': 'string', 'description': 'Lo que dijo el conductor, en sus palabras.'},
                },
                'required': ['guia_numero', 'novedad_tipo_id', 'motivo'],
            },
        },
    ]

    def system_prompt(self):
        return SYSTEM.format(empresa=self.empresa, conductor=self.conductor, despacho=self.despacho_id)

    def paso(self, mensajes):
        """Procesa el historial (que termina en un mensaje del conductor) y devuelve
        la respuesta de texto del agente. Corre el loop de tool-use hasta que el
        modelo responde texto (o se agota el tope de rondas).

        Devuelve {'texto': str, 'mensajes': historial_actualizado}.
        """
        mensajes = list(mensajes)
        system = self.system_prompt()
        for _ in range(MAX_RONDAS_TOOLS):
            r = self.llm.generar(system, mensajes, self.HERRAMIENTAS)
            if r.get('tool_calls'):
                mensajes.append({'rol': 'agente', 'texto': r.get('texto'), 'tool_calls': r['tool_calls']})
                for tc in r['tool_calls']:
                    resultado = self._ejecutar_tool(tc.get('nombre'), tc.get('args') or {})
                    mensajes.append({'rol': 'tool', 'nombre': tc.get('nombre'), 'resultado': resultado})
                continue
            texto = r.get('texto') or ''
            mensajes.append({'rol': 'agente', 'texto': texto})
            return {'texto': texto, 'mensajes': mensajes}
        # Se agotaron las rondas sin respuesta de texto: cierre seguro.
        cierre = 'Disculpá, tuve un problema procesando. Un compañero te va a contactar.'
        mensajes.append({'rol': 'agente', 'texto': cierre})
        logger.warning('Agente despacho %s: tope de rondas de tools sin texto final', self.despacho_id)
        return {'texto': cierre, 'mensajes': mensajes}

    # -- tools (reusan logica de ruteo; acotadas al despacho del contexto) --
    def _ejecutar_tool(self, nombre, args):
        try:
            if nombre == 'guias_pendientes':
                return self._t_guias_pendientes()
            if nombre == 'tipos_novedad':
                return self._t_tipos_novedad()
            if nombre == 'registrar_novedad':
                return self._t_registrar_novedad(args)
            return {'ok': False, 'error': f'tool desconocida: {nombre}'}
        except Exception as e:
            logger.exception('Agente despacho %s: error en tool %s', self.despacho_id, nombre)
            return {'ok': False, 'error': f'error interno ejecutando {nombre}'}

    def _t_guias_pendientes(self):
        qs = RutVisita.objects.filter(
            despacho_id=self.despacho_id, estado_entregado=False, estado_novedad=False,
        ).values('numero', 'destinatario', 'destinatario_direccion')[:MAX_GUIAS_LISTA + 1]
        filas = list(qs)
        truncado = len(filas) > MAX_GUIAS_LISTA
        guias = [
            {'guia': str(f['numero']), 'destinatario': f['destinatario'], 'direccion': f['destinatario_direccion']}
            for f in filas[:MAX_GUIAS_LISTA]
        ]
        return {'guias': guias, 'total': len(guias), 'truncado': truncado}

    def _t_tipos_novedad(self):
        tipos = list(RutNovedadTipo.objects.values('id', 'nombre'))
        return {'tipos': tipos}

    def _t_registrar_novedad(self, args):
        guia = str(args.get('guia_numero') or '').strip()
        tipo_id = args.get('novedad_tipo_id')
        motivo = (args.get('motivo') or '').strip()

        visita = RutVisita.objects.filter(despacho_id=self.despacho_id, numero=guia).first()
        if not visita:
            return {'ok': False, 'error': f'La guía {guia} no es de este viaje.'}
        if not RutNovedadTipo.objects.filter(pk=tipo_id).exists():
            return {'ok': False, 'error': f'El tipo de novedad {tipo_id} no existe.'}

        # Idempotencia: mismo (despacho, guía, tipo) no duplica (movil_token del service).
        token = f'agente:{self.despacho_id}:{visita.id}:{tipo_id}'
        registrar_novedad(
            visita=visita, novedad_tipo_id=tipo_id, fecha=timezone.now(),
            descripcion=motivo, movil_token=token, imagenes=[], tenant=self.tenant,
        )
        self.novedades_registradas.append({'guia': guia, 'tipo_id': tipo_id})
        return {'ok': True, 'guia': guia, 'tipo_id': tipo_id, 'mensaje': 'Novedad registrada.'}
