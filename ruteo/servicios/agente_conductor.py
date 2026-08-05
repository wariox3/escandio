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
- El conductor suele estar MANEJANDO: preferí que TOQUE opciones en vez de escribir. Usá \
`ofrecer_opciones` para que elija la guía (de guias_pendientes) y el tipo de novedad (de \
tipos_novedad). Pedí texto libre solo para el motivo, y corto.
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
        {
            'nombre': 'ofrecer_opciones',
            'descripcion': 'Muestra opciones para que el conductor las TOQUE en WhatsApp (en vez de escribir). Usalo para preguntar qué guía (con guias_pendientes) o qué tipo de novedad (con tipos_novedad). Con esto TERMINA tu turno: el conductor toca una y su elección llega como su próximo mensaje.',
            'parametros': {
                'type': 'object',
                'properties': {
                    'texto': {'type': 'string', 'description': 'Pregunta corta arriba de las opciones.'},
                    'opciones': {
                        'type': 'array',
                        'description': '2 a 10 opciones para tocar.',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'titulo': {'type': 'string', 'description': 'Texto corto que toca el conductor (guía o tipo).'},
                                'descripcion': {'type': 'string', 'description': 'Detalle opcional (ej. destinatario o dirección).'},
                            },
                            'required': ['titulo'],
                        },
                    },
                },
                'required': ['texto', 'opciones'],
            },
        },
    ]

    def system_prompt(self):
        return SYSTEM.format(empresa=self.empresa, conductor=self.conductor, despacho=self.despacho_id)

    def paso(self, mensajes):
        """Procesa el historial (que termina en un mensaje del conductor) y devuelve
        la respuesta del agente. Corre el loop de tool-use hasta que el modelo
        responde texto, ofrece opciones, o se agota el tope de rondas.

        Devuelve {'tipo': 'texto'|'botones'|'lista', 'texto': str,
                  'opciones'?: [...], 'mensajes': historial_actualizado}.
        """
        mensajes = list(mensajes)
        system = self.system_prompt()
        for _ in range(MAX_RONDAS_TOOLS):
            r = self.llm.generar(system, mensajes, self.HERRAMIENTAS)
            if r.get('tool_calls'):
                mensajes.append({'rol': 'agente', 'texto': r.get('texto'), 'tool_calls': r['tool_calls']})
                interactivo = None
                for tc in r['tool_calls']:
                    nombre = tc.get('nombre')
                    if nombre == 'ofrecer_opciones':
                        interactivo = self._construir_interactivo(tc.get('args') or {})
                        resultado = {'ok': True, 'enviado': True}
                    else:
                        resultado = self._ejecutar_tool(nombre, tc.get('args') or {})
                    mensajes.append({'rol': 'tool', 'nombre': nombre,
                                     'resultado': resultado, '_id': tc.get('_id')})
                if interactivo:
                    # Ofrecer opciones cierra el turno: se manda el interactivo y se
                    # espera el toque del conductor.
                    return {**interactivo, 'mensajes': mensajes}
                continue
            texto = r.get('texto') or ''
            mensajes.append({'rol': 'agente', 'texto': texto})
            return {'tipo': 'texto', 'texto': texto, 'mensajes': mensajes}
        # Se agotaron las rondas sin respuesta final: cierre seguro.
        cierre = 'Disculpá, tuve un problema procesando. Un compañero te va a contactar.'
        mensajes.append({'rol': 'agente', 'texto': cierre})
        logger.warning('Agente despacho %s: tope de rondas de tools sin respuesta final', self.despacho_id)
        return {'tipo': 'texto', 'texto': cierre, 'mensajes': mensajes}

    def _construir_interactivo(self, args):
        """Normaliza los args de ofrecer_opciones -> botones (<=3) o lista (>3)."""
        texto = (args.get('texto') or '¿Qué querés hacer?')[:1024]
        ops = [
            {'titulo': (o.get('titulo') or '').strip(), 'descripcion': (o.get('descripcion') or '').strip()}
            for o in (args.get('opciones') or []) if (o.get('titulo') or '').strip()
        ][:10]
        if not ops:
            return {'tipo': 'texto', 'texto': texto}
        return {'tipo': 'botones' if len(ops) <= 3 else 'lista', 'texto': texto, 'opciones': ops}

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


def procesar_entrante_conductor(telefono, texto, conexion, cliente_llm=None):
    """Orquesta un mensaje entrante del conductor.

    Si hay una sesion de agente ACTIVA para este telefono, corre el agente con
    el historial guardado, responde por WhatsApp y persiste. Devuelve la
    respuesta de texto, o None si NO hay sesion (el webhook sigue su curso
    normal, sin agente).

    El schema del tenant ya viene seteado por el webhook antes de llamar aca.
    """
    # Imports locales: evita ciclos al cargar apps (mensajeria <-> ruteo).
    from mensajeria.servicios.whatsapp_cliente import WhatsappCliente
    from ruteo.models.agente_sesion import RutAgenteSesion

    sesion = (
        RutAgenteSesion.objects
        .filter(telefono=telefono, estado=RutAgenteSesion.ESTADO_ACTIVA)
        .order_by('-id').first()
    )
    if not sesion:
        return None

    contenedor = getattr(conexion, 'contenedor', None)
    agente = AgenteConductor(
        despacho_id=sesion.despacho_id,
        tenant=contenedor,
        empresa=getattr(contenedor, 'nombre', None) or 'la empresa',
        conductor=sesion.conductor_nombre or 'conductor',
        cliente_llm=cliente_llm,
    )
    historial = list(sesion.historial or []) + [{'rol': 'usuario', 'texto': texto}]
    resultado = agente.paso(historial)

    sesion.historial = resultado['mensajes']
    sesion.save(update_fields=['historial', 'fecha_actualizacion'])

    try:
        _enviar_respuesta(WhatsappCliente(conexion), telefono, resultado)
    except Exception:
        logger.exception('Agente: fallo enviando respuesta a %s (despacho %s)', telefono, sesion.despacho_id)
    return resultado.get('texto', '')


def _enviar_respuesta(cliente, telefono, resultado):
    """Manda la respuesta del agente por el canal correcto segun su tipo."""
    tipo = resultado.get('tipo', 'texto')
    texto = resultado.get('texto', '')
    opciones = resultado.get('opciones') or []
    if tipo == 'botones':
        return cliente.enviar_botones(telefono, texto, opciones)
    if tipo == 'lista':
        return cliente.enviar_lista(telefono, texto, 'Elegir', opciones)
    return cliente.enviar_texto(telefono, texto)


def iniciar_sesion_conductor(despacho_id, telefono=None):
    """Arranque MANUAL desde Tráfico: crea (o reusa) la sesión del agente y le
    manda el saludo por WhatsApp.

    El `telefono` lo puede indicar el despachador: los despachos van por PLACA
    (sin conductor fijo), así que casi nunca hay un conductor del que sacar el
    número. Si no se indica, cae al teléfono del conductor asignado (si lo hay).

    Corre en el schema del tenant (lo setea la request). Devuelve
    {'ok', 'mensaje', 'sesion_id'?, 'telefono'?}. El teléfono se normaliza igual
    que el webhook para que el entrante del conductor matchee la sesión.
    """
    from contenedor.models import CtnWhatsappConexion, User
    from django.db import connection
    from mensajeria.servicios.whatsapp_cliente import WhatsappCliente
    from ruteo.models.agente_sesion import RutAgenteSesion
    from ruteo.models.despacho import RutDespacho
    from ruteo.servicios.notificacion import NotificacionServicio

    despacho = RutDespacho.objects.filter(pk=despacho_id).first()
    if not despacho:
        return {'ok': False, 'mensaje': 'El despacho no existe'}

    # El teléfono lo indica el despachador; si no, se resuelve del conductor
    # asignado (cuando el despacho tiene uno).
    user = User.objects.filter(pk=despacho.conductor_id).first() if despacho.conductor_id else None
    telefono = NotificacionServicio.normalizar_telefono(telefono or getattr(user, 'telefono', None))
    if not telefono:
        return {'ok': False, 'mensaje': 'Indicá un número de WhatsApp válido para escribirle'}

    conexion = (
        CtnWhatsappConexion.objects
        .filter(contenedor__schema_name=connection.schema_name, estado=CtnWhatsappConexion.ESTADO_ACTIVO)
        .select_related('contenedor').first()
    )
    if not conexion:
        return {'ok': False, 'mensaje': 'No hay conexión de WhatsApp activa para el contenedor'}

    # Reusar una conversación activa en vez de duplicarla / re-saludar.
    sesion = RutAgenteSesion.objects.filter(
        despacho_id=despacho_id, telefono=telefono, estado=RutAgenteSesion.ESTADO_ACTIVA,
    ).first()
    if sesion:
        return {'ok': True, 'mensaje': 'Ya había una conversación activa',
                'sesion_id': sesion.id, 'telefono': telefono}

    conductor = (f"{(user.nombre or '')} {(user.apellido or '')}".strip() if user else '') or 'conductor'
    empresa = getattr(conexion.contenedor, 'nombre', None) or 'la empresa'
    saludo = (
        f'¡Hola {conductor}! 👋 Soy el asistente de {empresa}. '
        f'Cerremos el viaje #{despacho_id}. ¿Tuviste alguna guía con novedad?'
    )
    opciones_saludo = [{'titulo': 'Reportar novedad'}, {'titulo': 'Sin novedades'}]
    sesion = RutAgenteSesion.objects.create(
        despacho_id=despacho_id, telefono=telefono, conductor_nombre=conductor,
        estado=RutAgenteSesion.ESTADO_ACTIVA,
        historial=[{'rol': 'agente', 'texto': saludo}],
    )
    try:
        WhatsappCliente(conexion).enviar_botones(telefono, saludo, opciones_saludo)
    except Exception:
        logger.exception('Agente: fallo enviando saludo a %s (despacho %s)', telefono, despacho_id)
        return {'ok': False, 'mensaje': 'No se pudo enviar el saludo por WhatsApp', 'sesion_id': sesion.id}

    return {'ok': True, 'mensaje': 'Conversación iniciada', 'sesion_id': sesion.id, 'telefono': telefono}
