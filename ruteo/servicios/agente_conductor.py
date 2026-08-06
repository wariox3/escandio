"""LOGY — asistente de conductores (piloto).

Le escribe al conductor por WhatsApp para registrar las NOVEDADES de las guías
que no se pudieron entregar. Las entregas OK no se tocan (requieren evidencia
foto/firma que por texto no hay).

El flujo es una MÁQUINA DE ESTADOS determinística (no LLM): la navegación
(menús, Volver, cancelar, confirmar) se resuelve en código, así es consistente y
confiable. El estado vive en `RutAgenteSesion.paso` + `.contexto`. El LLM se
reserva para un futuro fuzzy-match de texto libre; el flujo no depende de él.

Estados: menu → guia → tipo → motivo → confirma → otra → (cierre).
"""
import logging
import re
from datetime import timedelta

from django.utils import timezone

from movil.services.novedad import registrar_novedad
from ruteo.models.agente_sesion import RutAgenteSesion
from ruteo.models.novedad_tipo import RutNovedadTipo
from ruteo.models.visita import RutVisita

logger = logging.getLogger(__name__)

NOMBRE_AGENTE = 'LOGY'      # nombre con el que se presenta el asistente
HORAS_SESION_ACTIVA = 6     # tras este tiempo sin actividad, la sesión se cierra sola
MAX_GUIAS_FETCH = 60        # tope de guías que traemos para contar/matchear
MAX_GUIAS_MENU = 8          # guías tappables por menú (deja lugar a navegación en la lista)
MAX_TIPOS_MENU = 9          # tipos tappables (deja lugar al Volver)

# Fallback si algo del flujo explota: no dejamos al conductor sin respuesta ni
# mandamos un body vacío (Meta lo rechaza). Incluye 'compañero' a propósito.
MSJ_ERROR_TECNICO = 'Perdón, tuve un problema y no pude seguir. Un compañero te va a contactar. 🙏'

# Arranque self-service: el conductor manda su placa al terminar el viaje.
MAX_PALABRAS_PLACA = 6     # mensajes más largos NO se tratan como inicio por placa
DIAS_VENTANA_PLACA = 7     # antigüedad máxima del despacho que resolvemos por placa
_PLACA_RE = re.compile(r'[A-Z]{3}\s*-?\s*\d{2,3}[A-Z]?')


# ---------------------------------------------------------------------------
# Datos (acotados a un despacho; reusan la lógica de ruteo)
# ---------------------------------------------------------------------------
def _guias_pendientes(despacho_id):
    """Guías del viaje sin resolver (ni entregadas ni con novedad)."""
    qs = (RutVisita.objects
          .filter(despacho_id=despacho_id, estado_entregado=False, estado_novedad=False)
          .values('numero', 'destinatario', 'destinatario_direccion')
          .order_by('numero')[:MAX_GUIAS_FETCH])
    return list(qs)


def _tipos_novedad():
    return list(RutNovedadTipo.objects.values('id', 'nombre').order_by('id'))


def _registrar(despacho_id, guia_numero, tipo_id, motivo, tenant):
    """Registra la novedad (idempotente por movil_token). Devuelve (ok, mensaje)."""
    guia = str(guia_numero or '').strip()
    visita = RutVisita.objects.filter(despacho_id=despacho_id, numero=guia).first()
    if not visita:
        return False, f'La guía {guia} ya no está en el viaje.'
    if not RutNovedadTipo.objects.filter(pk=tipo_id).exists():
        return False, 'Ese tipo de novedad no existe.'
    token = f'agente:{despacho_id}:{visita.id}:{tipo_id}'
    registrar_novedad(
        visita=visita, novedad_tipo_id=tipo_id, fecha=timezone.now(),
        descripcion=(motivo or '').strip(), movil_token=token, imagenes=[], tenant=tenant,
    )
    return True, 'ok'


# ---------------------------------------------------------------------------
# Máquina de estados del flujo de novedades
# ---------------------------------------------------------------------------
class FlujoNovedades:
    """Procesa UN mensaje del conductor según el estado de la sesión y devuelve la
    respuesta a enviar: {'tipo': 'texto'|'botones'|'lista', 'texto', 'opciones'?,
    'boton'?}. Muta `sesion.paso`, `sesion.estado` y `self.ctx` (el orquestador
    persiste después)."""

    # Palabras de texto libre que equivalen a navegación.
    _NAV = {
        'menu': 'menu', 'menú': 'menu', 'inicio': 'menu', 'empezar': 'menu',
        'volver': 'volver', 'atras': 'volver', 'atrás': 'volver', 'regresar': 'volver', 'anterior': 'volver',
        'cancelar': 'cancelar', 'cancela': 'cancelar', 'me equivoque': 'cancelar', 'me equivoqué': 'cancelar',
        'listo': 'terminar', 'terminar': 'terminar', 'termine': 'terminar', 'terminé': 'terminar',
        'fin': 'terminar', 'no mas': 'terminar', 'no más': 'terminar',
        'ya termine': 'terminar', 'ya terminé': 'terminar',
    }

    def __init__(self, sesion, tenant):
        self.sesion = sesion
        self.tenant = tenant
        self.despacho_id = sesion.despacho_id
        self.ctx = dict(sesion.contexto or {})

    def procesar(self, texto, opcion_id=None):
        kind, val = self._intent(texto, opcion_id)
        # Comandos globales (en cualquier estado). 'volver' NO es global: es por-paso.
        if kind == 'nav' and val == 'menu':
            return self._ir_menu()
        if kind == 'nav' and val == 'cancelar':
            self.ctx.pop('guia', None); self.ctx.pop('tipo', None); self.ctx.pop('motivo', None)
            return self._ir_menu(prefijo='Listo, cancelé. ')
        if kind == 'nav' and val == 'terminar':
            return self._cerrar()
        handler = getattr(self, f'_en_{self.sesion.paso}', None)
        if handler is None:                       # estado desconocido -> reencauzar
            return self._ir_menu()
        return handler(kind, val, texto)

    def _intent(self, texto, opcion_id):
        """Normaliza la entrada a (kind, val). Un toque de botón trae id 'kind:val';
        el texto libre se mapea a navegación o queda como ('texto', <texto>)."""
        if opcion_id and ':' in opcion_id:
            kind, _, val = opcion_id.partition(':')
            return kind, val
        t = (texto or '').strip().lower()
        if t in self._NAV:
            return 'nav', self._NAV[t]
        return 'texto', (texto or '').strip()

    # -- handlers por estado ------------------------------------------------
    def _en_menu(self, kind, val, texto):
        if kind == 'menu' and val == 'reportar':
            return self._ir_guias()
        if kind == 'menu' and val == 'sin_novedades':
            return self._cerrar(sin_novedades=True)
        t = (texto or '').lower()
        if any(w in t for w in ('report', 'novedad', 'problema', 'no entreg', 'no pude', 'devol')):
            return self._ir_guias()
        if any(w in t for w in ('sin novedad', 'ninguna', 'nada', 'todo bien', 'entregue', 'entregué', 'entregado')):
            return self._cerrar(sin_novedades=True)
        return self._menu_principal(prefijo='No te seguí 🤔 ')

    def _en_guia(self, kind, val, texto):
        if kind == 'nav' and val == 'volver':
            return self._ir_menu()
        if kind == 'nav' and val == 'escribir':
            return {'tipo': 'texto', 'texto': 'Escribí el número de la guía 👇'}
        if kind == 'guia':
            return self._elegir_guia(val)
        if kind == 'texto':
            g = self._match_guia(texto)
            if g:
                return self._elegir_guia(g['numero'])
            return self._menu_guias(prefijo='No encontré esa guía. ')
        return self._menu_guias()

    def _en_tipo(self, kind, val, texto):
        if kind == 'nav' and val == 'volver':
            return self._ir_guias()
        if kind == 'tipo':
            return self._elegir_tipo(val)
        if kind == 'texto':
            tp = self._match_tipo(texto)
            if tp:
                return self._elegir_tipo(tp['id'])
            return self._menu_tipos(prefijo='No reconocí ese tipo. ')
        return self._menu_tipos()

    def _en_motivo(self, kind, val, texto):
        if kind == 'nav' and val == 'volver':
            self.sesion.paso = RutAgenteSesion.PASO_TIPO
            return self._menu_tipos()
        if kind == 'nav' and val == 'omitir':
            self.ctx['motivo'] = ''
            return self._ir_confirmar()
        if kind == 'texto' and (texto or '').strip():
            self.ctx['motivo'] = texto.strip()[:500]
            return self._ir_confirmar()
        return self._pedir_motivo()

    def _en_confirma(self, kind, val, texto):
        if kind == 'conf' and val == 'si':
            return self._registrar_y_seguir()
        if kind == 'conf' and val == 'corregir':
            self.sesion.paso = RutAgenteSesion.PASO_TIPO
            return self._menu_tipos(prefijo='Corrijamos. ')
        if kind == 'conf' and val == 'descartar':
            self.ctx.pop('guia', None); self.ctx.pop('tipo', None); self.ctx.pop('motivo', None)
            return self._ir_guias(prefijo='Listo, la descarté. ')
        if kind == 'nav' and val == 'volver':
            self.sesion.paso = RutAgenteSesion.PASO_TIPO
            return self._menu_tipos()
        return self._confirmar()

    def _en_otra(self, kind, val, texto):
        if kind == 'otra' and val == 'si':
            return self._ir_guias()
        if kind == 'otra' and val == 'no':
            return self._cerrar()
        t = (texto or '').lower()
        if any(w in t for w in ('otra', 'report', 'novedad', 'si', 'sí')):
            return self._ir_guias()
        if any(w in t for w in ('no', 'listo', 'termin', 'ya', 'nada')):
            return self._cerrar()
        return self._menu_otra()

    # -- transiciones -------------------------------------------------------
    def _elegir_guia(self, numero):
        g = self._buscar_guia(numero)
        if not g:
            return self._menu_guias(prefijo='Esa guía ya no está pendiente. ')
        self.ctx['guia'] = {'numero': str(g['numero']), 'nombre': g.get('destinatario') or ''}
        self.sesion.paso = RutAgenteSesion.PASO_TIPO
        return self._menu_tipos()

    def _elegir_tipo(self, tipo_id):
        tp = self._buscar_tipo(tipo_id)
        if not tp:
            return self._menu_tipos(prefijo='Ese tipo no existe. ')
        self.ctx['tipo'] = {'id': tp['id'], 'nombre': tp['nombre']}
        self.sesion.paso = RutAgenteSesion.PASO_MOTIVO
        return self._pedir_motivo()

    def _ir_confirmar(self):
        self.sesion.paso = RutAgenteSesion.PASO_CONFIRMA
        return self._confirmar()

    def _registrar_y_seguir(self):
        guia = self.ctx.get('guia') or {}
        tipo = self.ctx.get('tipo') or {}
        ok, msg = _registrar(self.despacho_id, guia.get('numero'), tipo.get('id'),
                             self.ctx.get('motivo', ''), self.tenant)
        self.ctx.pop('guia', None); self.ctx.pop('tipo', None); self.ctx.pop('motivo', None)
        if not ok:
            return self._ir_guias(prefijo=f'{msg} ')
        regs = self.ctx.get('registradas') or []
        if guia.get('numero') and guia['numero'] not in regs:
            regs.append(guia['numero'])
        self.ctx['registradas'] = regs
        self.sesion.paso = RutAgenteSesion.PASO_OTRA
        return self._menu_otra(prefijo=f'✅ Registré la novedad de la guía {guia.get("numero", "")}.\n')

    # -- constructores de mensaje ------------------------------------------
    def _ir_menu(self, prefijo=''):
        self.sesion.paso = RutAgenteSesion.PASO_MENU
        return self._menu_principal(prefijo=prefijo)

    def _menu_principal(self, prefijo=''):
        texto = prefijo + f'¿Cómo te fue con el viaje #{self.despacho_id}?'
        return self._opts(texto, [
            {'id': 'menu:reportar', 'titulo': '📋 Reportar novedad'},
            {'id': 'menu:sin_novedades', 'titulo': '✅ Sin novedades'},
        ])

    def _ir_guias(self, prefijo=''):
        self.sesion.paso = RutAgenteSesion.PASO_GUIA
        return self._menu_guias(prefijo=prefijo)

    def _menu_guias(self, prefijo=''):
        guias = _guias_pendientes(self.despacho_id)
        if not guias:
            return self._cerrar(sin_novedades=True, prefijo='Ya no quedan guías pendientes. ')
        opciones = []
        for g in guias[:MAX_GUIAS_MENU]:
            titulo = f'{g["numero"]} · {(g.get("destinatario") or "").strip()}'.strip(' ·')
            opciones.append({'id': f'guia:{g["numero"]}', 'titulo': titulo,
                             'descripcion': (g.get('destinatario_direccion') or '').strip()})
        if len(guias) > MAX_GUIAS_MENU:
            opciones.append({'id': 'nav:escribir', 'titulo': '✍️ Escribir número'})
        opciones.append({'id': 'nav:volver', 'titulo': '⬅️ Volver'})
        texto = prefijo + f'¿Qué guía tuvo novedad? (quedan {len(guias)})'
        return self._opts(texto, opciones, boton='Ver guías')

    def _menu_tipos(self, prefijo=''):
        tipos = _tipos_novedad()
        if not tipos:
            return self._ir_menu(prefijo='No hay tipos de novedad configurados. Avisá al despachador. ')
        guia = self.ctx.get('guia') or {}
        opciones = [{'id': f'tipo:{t["id"]}', 'titulo': t['nombre']} for t in tipos[:MAX_TIPOS_MENU]]
        opciones.append({'id': 'nav:volver', 'titulo': '⬅️ Volver'})
        texto = prefijo + f'Guía {guia.get("numero", "")} · {guia.get("nombre", "")}. ¿Qué pasó?'
        return self._opts(texto, opciones, boton='Ver tipos')

    def _pedir_motivo(self, prefijo=''):
        return self._opts(prefijo + 'Contame en pocas palabras qué pasó (o tocá Omitir).', [
            {'id': 'nav:omitir', 'titulo': '⏭️ Omitir'},
            {'id': 'nav:volver', 'titulo': '⬅️ Volver'},
        ])

    def _confirmar(self):
        guia = self.ctx.get('guia') or {}
        tipo = self.ctx.get('tipo') or {}
        motivo = self.ctx.get('motivo', '')
        lineas = ['Confirmá la novedad:',
                  f'📦 Guía {guia.get("numero", "")} · {guia.get("nombre", "")}',
                  f'⚠️ {tipo.get("nombre", "")}']
        if motivo:
            lineas.append(f'📝 "{motivo}"')
        return self._opts('\n'.join(lineas), [
            {'id': 'conf:si', 'titulo': '✅ Confirmar'},
            {'id': 'conf:corregir', 'titulo': '✏️ Corregir'},
            {'id': 'conf:descartar', 'titulo': '❌ Descartar'},
        ])

    def _menu_otra(self, prefijo=''):
        self.sesion.paso = RutAgenteSesion.PASO_OTRA
        return self._opts(prefijo + '¿Otra guía con novedad?', [
            {'id': 'otra:si', 'titulo': '📋 Reportar otra'},
            {'id': 'otra:no', 'titulo': '🏁 Terminar'},
        ])

    def _cerrar(self, sin_novedades=False, prefijo=''):
        self.sesion.estado = RutAgenteSesion.ESTADO_CERRADA
        self.sesion.paso = RutAgenteSesion.PASO_MENU
        regs = self.ctx.get('registradas') or []
        if regs:
            plural = 'es' if len(regs) != 1 else ''
            resumen = f'Registré {len(regs)} novedad{plural}: guía{"s" if len(regs) != 1 else ""} {", ".join(regs)}.'
        elif sin_novedades:
            resumen = 'Sin novedades en este viaje. 👍'
        else:
            resumen = 'No quedó ninguna novedad registrada.'
        texto = f'{prefijo}🏁 Cerramos el viaje #{self.despacho_id}.\n{resumen}\n¡Gracias, buen camino! 🚚💨'
        return {'tipo': 'texto', 'texto': texto}

    def _opts(self, texto, opciones, boton='Elegir'):
        """Arma la respuesta interactiva: botones si son <=3, lista si son más."""
        tipo = 'botones' if len(opciones) <= 3 else 'lista'
        return {'tipo': tipo, 'texto': texto[:1024], 'opciones': opciones, 'boton': boton}

    # -- matching de texto libre -------------------------------------------
    def _buscar_guia(self, numero):
        num = str(numero).strip()
        for g in _guias_pendientes(self.despacho_id):
            if str(g['numero']) == num:
                return g
        return None

    def _match_guia(self, texto):
        t = (texto or '').strip().lower()
        if not t:
            return None
        guias = _guias_pendientes(self.despacho_id)
        digitos = re.sub(r'\D', '', t)
        if digitos:
            for g in guias:
                if str(g['numero']) == digitos:
                    return g
        for g in guias:
            nom = (g.get('destinatario') or '').lower()
            if nom and (nom in t or t in nom):
                return g
        return None

    def _buscar_tipo(self, tipo_id):
        try:
            tid = int(tipo_id)
        except (TypeError, ValueError):
            return None
        for t in _tipos_novedad():
            if t['id'] == tid:
                return t
        return None

    def _match_tipo(self, texto):
        t = (texto or '').strip().lower()
        if not t:
            return None
        for tp in _tipos_novedad():
            nom = (tp['nombre'] or '').lower()
            if nom and (nom in t or t in nom):
                return tp
        return None


# ---------------------------------------------------------------------------
# Orquestador (webhook -> flujo -> WhatsApp)
# ---------------------------------------------------------------------------
def procesar_entrante_conductor(telefono, texto, conexion, opcion_id=None):
    """Orquesta un mensaje entrante del conductor.

    - Sesión ACTIVA para este teléfono -> corre la máquina de estados y responde.
    - Sin sesión -> intenta ARRANCAR por placa (self-service, con auth híbrida).
    - Nada matchea -> devuelve None (el mensaje sigue al inbox normal).

    `opcion_id` es el id del botón/fila que tocó el conductor (ej. 'guia:6733712');
    None si escribió texto. El schema del tenant ya viene seteado por el webhook.
    """
    from mensajeria.servicios.whatsapp_cliente import WhatsappCliente

    # Cierra sesiones abandonadas (sin actividad hace rato): no quedan "activas"
    # para siempre bloqueando el próximo viaje del mismo número.
    limite = timezone.now() - timedelta(hours=HORAS_SESION_ACTIVA)
    RutAgenteSesion.objects.filter(
        telefono=telefono, estado=RutAgenteSesion.ESTADO_ACTIVA,
        fecha_actualizacion__lt=limite,
    ).update(estado=RutAgenteSesion.ESTADO_CERRADA)

    sesion = (
        RutAgenteSesion.objects
        .filter(telefono=telefono, estado=RutAgenteSesion.ESTADO_ACTIVA,
                fecha_actualizacion__gte=limite)
        .order_by('-id').first()
    )
    if not sesion:
        despacho = _resolver_despacho_por_placa(texto)
        if despacho:
            esperado = _telefono_esperado(despacho)
            if esperado and not _mismo_numero(esperado, telefono):
                logger.warning('LOGY: %s intentó arrancar el viaje %s por placa, pero no es '
                               'el número autorizado; se ignora.', telefono, despacho.id)
                return None
            nueva, _envio = _arrancar_sesion(conexion, despacho.id, telefono, _nombre_conductor(despacho))
            if not nueva:
                return None
            return nueva.historial[-1]['texto'] if nueva.historial else ''
        # No hay placa: a un texto CORTO lo saludamos y le pedimos la placa, así el
        # conductor que escribe suelto (un "hola") no queda sin respuesta. Un texto
        # largo o un toque de botón huérfano probablemente sea un cliente -> lo
        # dejamos pasar al inbox humano sin auto-responder.
        if opcion_id or len((texto or '').split()) > MAX_PALABRAS_PLACA:
            return None
        return _bienvenida(conexion, telefono)

    tenant = getattr(conexion, 'contenedor', None)
    flujo = FlujoNovedades(sesion, tenant)
    try:
        respuesta = flujo.procesar(texto, opcion_id)
    except Exception:
        logger.exception('LOGY: el flujo falló para %s (despacho %s)', telefono, sesion.despacho_id)
        respuesta = {'tipo': 'texto', 'texto': MSJ_ERROR_TECNICO}

    sesion.contexto = flujo.ctx
    hist = list(sesion.historial or [])
    hist.append({'rol': 'usuario', 'texto': texto, 'opcion': opcion_id})
    hist.append({'rol': 'agente', 'texto': respuesta.get('texto', '')})
    sesion.historial = hist[-40:]   # transcripción acotada
    sesion.save(update_fields=['paso', 'contexto', 'estado', 'historial', 'fecha_actualizacion'])

    try:
        envio = _enviar_respuesta(WhatsappCliente(conexion), telefono, respuesta)
        if isinstance(envio, dict) and envio.get('error'):
            logger.error('LOGY: Meta rechazó la respuesta a %s (despacho %s): %s',
                         telefono, sesion.despacho_id, envio.get('mensaje'))
    except Exception:
        logger.exception('LOGY: fallo enviando respuesta a %s (despacho %s)', telefono, sesion.despacho_id)
    return respuesta.get('texto', '')


def _enviar_respuesta(cliente, telefono, respuesta):
    """Manda la respuesta por el canal correcto. Nunca body vacío ni interactivo
    sin opciones (Meta los rechaza): cae a texto con un fallback."""
    tipo = respuesta.get('tipo', 'texto')
    texto = (respuesta.get('texto') or '').strip()
    opciones = respuesta.get('opciones') or []
    boton = respuesta.get('boton') or 'Elegir'
    if tipo == 'botones' and opciones:
        return cliente.enviar_botones(telefono, texto or '¿Qué querés hacer?', opciones)
    if tipo == 'lista' and opciones:
        return cliente.enviar_lista(telefono, texto or '¿Qué querés hacer?', boton, opciones)
    return cliente.enviar_texto(telefono, texto or MSJ_ERROR_TECNICO)


# ---------------------------------------------------------------------------
# Arranque por placa + autorización híbrida
# ---------------------------------------------------------------------------
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

    Solo matchea mensajes cortos (para no secuestrar mensajes largos de clientes)
    contra despachos aprobados, no anulados, de los últimos días.
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


def _mismo_numero(a, b):
    """Compara dos teléfonos por sus últimos 10 dígitos (ignora prefijos país/formato)."""
    da = re.sub(r'\D', '', str(a or ''))[-10:]
    db = re.sub(r'\D', '', str(b or ''))[-10:]
    return len(da) == 10 and da == db


def _telefono_esperado(despacho):
    """Teléfono autorizado para arrancar este viaje por placa (crudo), o None.

    Si el viaje tiene un número registrado (el que cargó el despachador, o el del
    conductor asignado), SOLO ese número puede arrancar LOGY. Si no hay ninguno,
    devuelve None y cualquiera con la placa puede (self-service).
    """
    from contenedor.models import User
    tel = getattr(despacho, 'conductor_telefono', None)
    if not tel and despacho.conductor_id:
        user = User.objects.filter(pk=despacho.conductor_id).first()
        tel = getattr(user, 'telefono', None)
    return tel or None


def _nombre_conductor(despacho):
    """Nombre del conductor asignado al despacho (si hay); si no, 'conductor'."""
    from contenedor.models import User
    user = User.objects.filter(pk=despacho.conductor_id).first() if despacho.conductor_id else None
    nombre = f"{(user.nombre or '')} {(user.apellido or '')}".strip() if user else ''
    return nombre or 'conductor'


def _bienvenida(conexion, telefono):
    """Saluda a un texto corto sin sesión y le pide la placa (no crea sesión: la
    placa es la que arranca el flujo). Devuelve el saludo, o None si no se pudo
    enviar. Así el conductor que escribe suelto no queda sin respuesta."""
    from mensajeria.servicios.whatsapp_cliente import WhatsappCliente

    empresa = getattr(getattr(conexion, 'contenedor', None), 'nombre', None) or 'la empresa'
    saludo = (
        f'¡Hola! 👋 Soy {NOMBRE_AGENTE}, el asistente de {empresa}. '
        f'Para cerrar tu viaje y reportar novedades, escribime tu *placa* (ej. ABC123).'
    )
    try:
        envio = WhatsappCliente(conexion).enviar_texto(telefono, saludo)
    except Exception:
        logger.exception('LOGY: fallo enviando la bienvenida a %s', telefono)
        return None
    if isinstance(envio, dict) and envio.get('error'):
        logger.error('LOGY: Meta rechazó la bienvenida a %s: %s', telefono, envio.get('mensaje'))
        return None
    return saludo


def _arrancar_sesion(conexion, despacho_id, telefono, conductor_nombre):
    """Manda el saludo + menú principal con botones y, si Meta lo acepta, crea la
    sesión ACTIVA en paso 'menu'. Devuelve (sesion, envio); sesion=None si el envío
    falló, para no dejar sesión fantasma."""
    from mensajeria.servicios.whatsapp_cliente import WhatsappCliente

    empresa = getattr(getattr(conexion, 'contenedor', None), 'nombre', None) or 'la empresa'
    saludo = (
        f'¡Hola {conductor_nombre}! 👋 Soy {NOMBRE_AGENTE}, el asistente de {empresa}. '
        f'Cerremos el viaje #{despacho_id}. ¿Cómo te fue?'
    )
    opciones = [
        {'id': 'menu:reportar', 'titulo': '📋 Reportar novedad'},
        {'id': 'menu:sin_novedades', 'titulo': '✅ Sin novedades'},
    ]
    try:
        envio = WhatsappCliente(conexion).enviar_botones(telefono, saludo, opciones)
    except Exception:
        logger.exception('LOGY: fallo enviando saludo a %s (despacho %s)', telefono, despacho_id)
        return None, {'error': True, 'mensaje': 'Excepción enviando el saludo por WhatsApp'}
    if isinstance(envio, dict) and envio.get('error'):
        logger.error('LOGY: Meta rechazó el saludo a %s (despacho %s): %s',
                     telefono, despacho_id, envio.get('mensaje'))
        return None, envio
    sesion = RutAgenteSesion.objects.create(
        despacho_id=despacho_id, telefono=telefono, conductor_nombre=conductor_nombre,
        estado=RutAgenteSesion.ESTADO_ACTIVA, paso=RutAgenteSesion.PASO_MENU,
        contexto={}, historial=[{'rol': 'agente', 'texto': saludo}],
    )
    return sesion, envio


def iniciar_sesion_conductor(despacho_id, telefono=None):
    """Arranque MANUAL desde Tráfico: crea (o reusa) la sesión y manda el saludo.

    El `telefono` lo indica el despachador; si no, se resuelve del conductor
    asignado (cuando lo hay). Corre en el schema del tenant. Devuelve
    {'ok', 'mensaje', 'sesion_id'?, 'telefono'?}.
    """
    from contenedor.models import CtnWhatsappConexion, User
    from django.db import connection
    from ruteo.models.despacho import RutDespacho
    from ruteo.servicios.notificacion import NotificacionServicio

    despacho = RutDespacho.objects.filter(pk=despacho_id).first()
    if not despacho:
        return {'ok': False, 'mensaje': 'El despacho no existe'}

    user = User.objects.filter(pk=despacho.conductor_id).first() if despacho.conductor_id else None
    telefono = NotificacionServicio.normalizar_telefono(telefono or getattr(user, 'telefono', None))
    if not telefono:
        return {'ok': False, 'mensaje': 'Indicá un número de WhatsApp válido para escribirle'}

    # Registrar el número como autorizado para este viaje (hybrid): el arranque por
    # placa luego solo lo permite desde este número.
    if despacho.conductor_telefono != telefono:
        despacho.conductor_telefono = telefono
        despacho.save(update_fields=['conductor_telefono'])

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
    sesion, envio = _arrancar_sesion(conexion, despacho_id, telefono, conductor)
    if not sesion:
        detalle = (envio or {}).get('mensaje') or 'WhatsApp rechazó el mensaje'
        return {'ok': False, 'mensaje': f'No se pudo enviar el saludo: {detalle}'}
    return {'ok': True, 'mensaje': 'Conversación iniciada', 'sesion_id': sesion.id, 'telefono': telefono}
