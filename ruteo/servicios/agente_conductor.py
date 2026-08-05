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
import re
from datetime import timedelta

from django.utils import timezone

from movil.services.novedad import registrar_novedad
from ruteo.models.novedad_tipo import RutNovedadTipo
from ruteo.models.visita import RutVisita
from utilidades.llm import crear_cliente

logger = logging.getLogger(__name__)

NOMBRE_AGENTE = 'LOGY'    # nombre con el que se presenta el asistente al conductor
MAX_RONDAS_TOOLS = 6      # tope de rondas de tool-use por mensaje (anti-loop)
MAX_GUIAS_LISTA = 60      # tope de guias que enumeramos al modelo
MAX_OPCIONES = 10         # tope de opciones tocables (limite de Meta para listas)

# Fallback cuando el agente no puede continuar (excepcion del LLM/tool, tope de
# rondas, o respuesta vacia del modelo): no dejamos al conductor sin respuesta ni
# mandamos un body vacio (Meta lo rechaza). Incluye 'compañero' a proposito.
MSJ_ERROR_TECNICO = 'Perdón, tuve un problema y no pude seguir. Un compañero te va a contactar. 🙏'

# Arranque self-service: el conductor manda su placa al terminar el viaje.
MAX_PALABRAS_PLACA = 6     # mensajes más largos NO se tratan como inicio por placa
DIAS_VENTANA_PLACA = 7     # antigüedad máxima del despacho que resolvemos por placa
_PLACA_RE = re.compile(r'[A-Z]{3}\s*-?\s*\d{2,3}[A-Z]?')

SYSTEM = """\
Sos {agente}, el asistente de {empresa} que le escribe por WhatsApp al conductor {conductor} \
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
`ofrecer_opciones` para que elija la guía (de guias_pendientes) o el tipo de novedad (de \
tipos_novedad). Cada opción debe ser CORTA; si es una guía, empezá por el número \
(ej. "200002 - Ana") para que no se pierda al recortarse. Ofrecé como máximo 10 opciones: \
si quedan más guías pendientes, pedile que ESCRIBA el número de la guía. Pedí texto libre \
solo para el motivo, y corto.
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
        return SYSTEM.format(agente=NOMBRE_AGENTE, empresa=self.empresa,
                             conductor=self.conductor, despacho=self.despacho_id)

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
            texto = (r.get('texto') or '').strip()
            if not texto:
                # Modelo respondió vacío: Meta rechaza un body vacío -> fallback.
                logger.warning('Agente despacho %s: respuesta vacía del modelo', self.despacho_id)
                texto = MSJ_ERROR_TECNICO
            mensajes.append({'rol': 'agente', 'texto': texto})
            return {'tipo': 'texto', 'texto': texto, 'mensajes': mensajes}
        # Se agotaron las rondas sin respuesta final: cierre seguro.
        mensajes.append({'rol': 'agente', 'texto': MSJ_ERROR_TECNICO})
        logger.warning('Agente despacho %s: tope de rondas de tools sin respuesta final', self.despacho_id)
        return {'tipo': 'texto', 'texto': MSJ_ERROR_TECNICO, 'mensajes': mensajes}

    def _construir_interactivo(self, args):
        """Normaliza los args de ofrecer_opciones -> botones (<=3) o lista (>3).

        Defensivo: el modelo a veces manda 'opciones' que no es lista, items que
        son strings sueltos, o dicts sin 'titulo'. Nada de eso debe tumbar el turno
        (peor caso: degradar a texto).
        """
        if not isinstance(args, dict):
            args = {}
        texto = (str(args.get('texto') or '') or '¿Qué querés hacer?')[:1024]
        crudas = args.get('opciones')
        if not isinstance(crudas, (list, tuple)):
            crudas = []
        ops = []
        for o in crudas:
            if isinstance(o, dict):
                titulo = str(o.get('titulo') or '').strip()
                desc = str(o.get('descripcion') or '').strip()
            else:
                titulo = str(o if o is not None else '').strip()  # string suelto
                desc = ''
            if titulo:
                ops.append({'titulo': titulo, 'descripcion': desc})
            if len(ops) >= MAX_OPCIONES:
                break
        if not ops:
            # Sin opciones válidas: degradar a texto (Meta rechaza interactivos vacíos).
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

    - Si hay una sesion ACTIVA para este telefono, corre el agente con el historial
      guardado, responde por WhatsApp y persiste.
    - Si NO hay sesion, intenta ARRANCAR por placa: si el texto trae la placa de un
      despacho activo reciente, crea la sesion y saluda (arranque self-service).
    - Si no matchea nada, devuelve None y el webhook sigue su curso normal (inbox),
      sin secuestrar mensajes de clientes.

    Devuelve el texto de la respuesta/saludo, o None. El schema del tenant ya viene
    seteado por el webhook antes de llamar aca.
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
        # No hay conversación en curso: ¿el conductor mandó su placa para arrancar?
        # Arranque self-service. No secuestra mensajes ajenos: exige la placa de un
        # despacho activo reciente y un mensaje corto.
        despacho = _resolver_despacho_por_placa(texto)
        if not despacho:
            return None   # no es para el agente -> sigue al inbox normal
        nueva, _envio = _saludar_y_crear_sesion(conexion, despacho.id, telefono, _nombre_conductor(despacho))
        if not nueva:
            return None   # Meta rechazó el saludo (raro: el conductor acaba de escribir)
        return nueva.historial[-1]['texto'] if nueva.historial else ''

    contenedor = getattr(conexion, 'contenedor', None)
    agente = AgenteConductor(
        despacho_id=sesion.despacho_id,
        tenant=contenedor,
        empresa=getattr(contenedor, 'nombre', None) or 'la empresa',
        conductor=sesion.conductor_nombre or 'conductor',
        cliente_llm=cliente_llm,
    )
    historial = list(sesion.historial or []) + [{'rol': 'usuario', 'texto': texto}]
    try:
        resultado = agente.paso(historial)
    except Exception:
        # El LLM o una tool explotó (red, timeout, cuota): no perdemos el turno del
        # conductor -> guardamos su mensaje y respondemos un fallback.
        logger.exception('Agente: paso() falló para %s (despacho %s)', telefono, sesion.despacho_id)
        resultado = {
            'tipo': 'texto', 'texto': MSJ_ERROR_TECNICO,
            'mensajes': historial + [{'rol': 'agente', 'texto': MSJ_ERROR_TECNICO}],
        }

    sesion.historial = resultado['mensajes']
    sesion.save(update_fields=['historial', 'fecha_actualizacion'])

    try:
        envio = _enviar_respuesta(WhatsappCliente(conexion), telefono, resultado)
        if isinstance(envio, dict) and envio.get('error'):
            # Meta rechazó el envío (p.ej. fuera de la ventana de 24h): no crashea,
            # pero lo dejamos en el log para diagnosticar por qué no llegó.
            logger.error('Agente: Meta rechazó la respuesta a %s (despacho %s): %s',
                         telefono, sesion.despacho_id, envio.get('mensaje'))
    except Exception:
        logger.exception('Agente: fallo enviando respuesta a %s (despacho %s)', telefono, sesion.despacho_id)
    return resultado.get('texto', '')


def _enviar_respuesta(cliente, telefono, resultado):
    """Manda la respuesta del agente por el canal correcto segun su tipo.

    Nunca manda un body vacío ni un interactivo sin opciones (Meta los rechaza):
    cae a texto con un fallback.
    """
    tipo = resultado.get('tipo', 'texto')
    texto = (resultado.get('texto') or '').strip()
    opciones = resultado.get('opciones') or []
    if tipo == 'botones' and opciones:
        return cliente.enviar_botones(telefono, texto or '¿Qué querés hacer?', opciones)
    if tipo == 'lista' and opciones:
        return cliente.enviar_lista(telefono, texto or '¿Qué querés hacer?', 'Elegir', opciones)
    return cliente.enviar_texto(telefono, texto or MSJ_ERROR_TECNICO)


def _extraer_placas(texto):
    """Candidatos a placa dentro del texto, normalizados (sin separadores)."""
    placas = []
    for m in _PLACA_RE.finditer((texto or '').upper()):
        norm = re.sub(r'[^A-Z0-9]', '', m.group())
        if norm and norm not in placas:
            placas.append(norm)
    return placas


def _resolver_despacho_por_placa(texto):
    """Si el texto trae la placa de un despacho activo reciente, lo devuelve.

    Arranque self-service: el conductor manda su placa al terminar. Solo matchea
    mensajes cortos (para no secuestrar mensajes largos de clientes) contra
    despachos aprobados, no anulados, de los últimos días.
    """
    from django.db.models import Q
    from ruteo.models.despacho import RutDespacho

    if len((texto or '').split()) > MAX_PALABRAS_PLACA:
        return None
    placas = _extraer_placas(texto)
    if not placas:
        return None
    limite = timezone.now() - timedelta(days=DIAS_VENTANA_PLACA)
    for placa in placas:
        despacho = (
            RutDespacho.objects
            .filter(Q(fecha__gte=limite) | Q(fecha__isnull=True),
                    vehiculo__placa__iexact=placa,
                    estado_aprobado=True, estado_anulado=False)
            .order_by('-id').first()
        )
        if despacho:
            return despacho
    return None


def _nombre_conductor(despacho):
    """Nombre del conductor asignado al despacho (si hay); si no, 'conductor'."""
    from contenedor.models import User
    user = User.objects.filter(pk=despacho.conductor_id).first() if despacho.conductor_id else None
    nombre = f"{(user.nombre or '')} {(user.apellido or '')}".strip() if user else ''
    return nombre or 'conductor'


def _saludar_y_crear_sesion(conexion, despacho_id, telefono, conductor_nombre):
    """Manda el saludo con botones y, si Meta lo acepta, crea la sesión ACTIVA.

    Compartido por el arranque manual (Tráfico) y el automático (placa). Devuelve
    (sesion, envio); sesion=None si el envío falló, para no dejar sesión fantasma.
    """
    from mensajeria.servicios.whatsapp_cliente import WhatsappCliente
    from ruteo.models.agente_sesion import RutAgenteSesion

    empresa = getattr(getattr(conexion, 'contenedor', None), 'nombre', None) or 'la empresa'
    saludo = (
        f'¡Hola {conductor_nombre}! 👋 Soy {NOMBRE_AGENTE}, el asistente de {empresa}. '
        f'Cerremos el viaje #{despacho_id}. ¿Tuviste alguna guía con novedad?'
    )
    opciones = [{'titulo': 'Reportar novedad'}, {'titulo': 'Sin novedades'}]
    try:
        envio = WhatsappCliente(conexion).enviar_botones(telefono, saludo, opciones)
    except Exception:
        logger.exception('Agente: fallo enviando saludo a %s (despacho %s)', telefono, despacho_id)
        return None, {'error': True, 'mensaje': 'Excepción enviando el saludo por WhatsApp'}
    if isinstance(envio, dict) and envio.get('error'):
        logger.error('Agente: Meta rechazó el saludo a %s (despacho %s): %s',
                     telefono, despacho_id, envio.get('mensaje'))
        return None, envio
    sesion = RutAgenteSesion.objects.create(
        despacho_id=despacho_id, telefono=telefono, conductor_nombre=conductor_nombre,
        estado=RutAgenteSesion.ESTADO_ACTIVA,
        historial=[{'rol': 'agente', 'texto': saludo}],
    )
    return sesion, envio


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

    # El saludo se manda ANTES de crear la sesión (dentro del helper): si WhatsApp
    # lo rechaza (típico: el conductor no escribió en 24h y Meta exige plantilla),
    # no queda sesión "activa" fantasma y el despachador puede reintentar.
    sesion, envio = _saludar_y_crear_sesion(conexion, despacho_id, telefono, conductor)
    if not sesion:
        detalle = (envio or {}).get('mensaje') or 'WhatsApp rechazó el mensaje'
        return {'ok': False, 'mensaje': f'No se pudo enviar el saludo: {detalle}'}
    return {'ok': True, 'mensaje': 'Conversación iniciada', 'sesion_id': sesion.id, 'telefono': telefono}
