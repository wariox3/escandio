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

from decouple import config
from django.db import connection
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

# Handoff a un asesor humano: el bot pausa y la conversación queda para el inbox.
MSJ_A_ASESOR = ('Te paso con un asesor 🙋 En un momento te atienden por acá. '
                '(Cuando quieras volver al asistente, escribí tu placa.)')
MSJ_ERROR_A_ASESOR = ('Perdón, esto se me complicó 🙏 Te paso con un asesor, '
                      'en un momento te atienden por acá.')
# Frases con las que el conductor pide hablar con una persona. Distintivas, para no
# confundirlas con el motivo de una novedad ("no había persona", etc.).
_PIDE_HUMANO = ('asesor', 'humano', 'operador', 'soporte',
                'hablar con alguien', 'con una persona', 'un compañero', 'una compañera')

# Arranque self-service: el conductor manda su placa al terminar el viaje.
MAX_PALABRAS_PLACA = 6     # mensajes más largos NO se tratan como inicio por placa
# Antigüedad máxima (días) del despacho que resolvemos por placa/número. Configurable
# por entorno: en QA se puede subir (ej. 400) para probar con data vieja; prod deja 7.
DIAS_VENTANA_PLACA = config('LOGY_DIAS_VENTANA_PLACA', default=7, cast=int)
_PLACA_RE = re.compile(r'[A-Z]{3}\s*-?\s*\d{2,3}[A-Z]?')


# ---------------------------------------------------------------------------
# Datos (acotados a un despacho; reusan la lógica de ruteo)
# ---------------------------------------------------------------------------
def _guias_pendientes(despacho_id):
    """Guías del viaje sin resolver (ni entregadas ni con novedad). Incluye el id
    interno de la visita, que es el identificador estable (el número puede faltar)."""
    qs = (RutVisita.objects
          .filter(despacho_id=despacho_id, estado_entregado=False, estado_novedad=False)
          .values('id', 'numero', 'destinatario', 'destinatario_direccion')
          .order_by('id')[:MAX_GUIAS_FETCH])
    return list(qs)


def _etiqueta_guia(g):
    """Cómo se muestra la guía al conductor: su número, o un fallback si no tiene
    (nunca 'None')."""
    num = str(g.get('numero') or '').strip()
    return num or f'#{g["id"]}'


def _tipos_novedad():
    return list(RutNovedadTipo.objects.values('id', 'nombre').order_by('id'))


def _registrar(despacho_id, visita_id, tipo_id, motivo, tenant):
    """Registra la novedad de una visita (por id, idempotente). Devuelve (ok, mensaje)."""
    visita = RutVisita.objects.filter(despacho_id=despacho_id, id=visita_id).first()
    if not visita:
        return False, 'Esa guía ya no está en el viaje.'
    if not RutNovedadTipo.objects.filter(pk=tipo_id).exists():
        return False, 'Ese tipo de novedad no existe.'
    token = f'agente:{despacho_id}:{visita.id}:{tipo_id}'
    try:
        registrar_novedad(
            visita=visita, novedad_tipo_id=tipo_id, fecha=timezone.now(),
            descripcion=(motivo or '').strip(), movil_token=token, imagenes=[], tenant=tenant,
        )
    except Exception:
        # La novedad puede haber quedado escrita y fallar solo la notificación: no
        # tumbamos el flujo. Confirmamos por el estado real de la visita.
        logger.exception('LOGY: registrar_novedad falló (despacho %s, visita %s)', despacho_id, visita.id)
    finally:
        # registrar_novedad -> _notificar consulta modelos shared y deja la conexión
        # en schema 'public'. Reafirmamos el schema del tenant antes de seguir con
        # ORM de tenant (el refresh_from_db de acá y el sesion.save() aguas arriba):
        # si no, corren en 'public', la tabla del modelo de tenant no existe y la
        # confirmación al conductor nunca se envía (aunque la novedad SÍ quedó
        # grabada). Ver tests_agente_conductor.test_registrar_no_deja_schema_public.
        _schema = getattr(tenant, 'schema_name', None)
        if _schema:
            connection.set_schema(_schema)
    visita.refresh_from_db()
    if visita.estado_novedad:
        return True, 'ok'
    return False, 'No pude registrar la novedad. Un compañero la va a revisar.'


def _menu_opciones():
    """Opciones del menú principal del conductor (las comparten el saludo y el flujo)."""
    return [
        {'id': 'menu:guias', 'titulo': '📦 Mis guías'},
        {'id': 'menu:reportar', 'titulo': '📋 Reportar novedad'},
        {'id': 'menu:sin_novedades', 'titulo': '🏁 Terminar'},
    ]


def _resumen_viaje(despacho_id):
    """Contadores del viaje para el resumen (calculados de las visitas reales)."""
    qs = RutVisita.objects.filter(despacho_id=despacho_id)
    return {
        'total': qs.count(),
        'entregadas': qs.filter(estado_entregado=True).count(),
        'novedad': qs.filter(estado_novedad=True).count(),
        'pendientes': qs.filter(estado_entregado=False, estado_novedad=False).count(),
    }


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
        # Si el conductor pide una persona -> pasar a un asesor. No en el paso del
        # motivo, donde el texto libre es el contenido de la novedad.
        if kind == 'texto' and self.sesion.paso != RutAgenteSesion.PASO_MOTIVO \
                and self._pide_humano(texto):
            return self._pasar_a_humano()
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
        if kind == 'menu' and val == 'guias':
            return self._resumen()
        if kind == 'menu' and val == 'sin_novedades':
            return self._cerrar(sin_novedades=True)
        t = (texto or '').lower()
        if any(w in t for w in ('report', 'novedad', 'problema', 'no entreg', 'no pude', 'devol')):
            return self._ir_guias()
        if any(w in t for w in ('cuant', 'quedan', 'pendient', 'resumen', 'mis guia', 'mis guía')):
            return self._resumen()
        if any(w in t for w in ('sin novedad', 'ninguna', 'nada', 'todo bien', 'entregue', 'entregué', 'entregado', 'termin')):
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
                return self._elegir_guia(g['id'])
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
    def _elegir_guia(self, vid):
        g = self._buscar_guia(vid)
        if not g:
            return self._menu_guias(prefijo='Esa guía ya no está pendiente. ')
        self.ctx['guia'] = {'id': g['id'], 'etiqueta': _etiqueta_guia(g), 'nombre': g.get('destinatario') or ''}
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
        ok, msg = _registrar(self.despacho_id, guia.get('id'), tipo.get('id'),
                             self.ctx.get('motivo', ''), self.tenant)
        self.ctx.pop('guia', None); self.ctx.pop('tipo', None); self.ctx.pop('motivo', None)
        if not ok:
            return self._ir_guias(prefijo=f'{msg} ')
        etiqueta = guia.get('etiqueta') or ''
        regs = self.ctx.get('registradas') or []
        if etiqueta and etiqueta not in regs:
            regs.append(etiqueta)
        self.ctx['registradas'] = regs
        self.sesion.paso = RutAgenteSesion.PASO_OTRA
        return self._menu_otra(prefijo=f'✅ Registré la novedad de la guía {etiqueta}.\n')

    # -- constructores de mensaje ------------------------------------------
    def _ir_menu(self, prefijo=''):
        self.sesion.paso = RutAgenteSesion.PASO_MENU
        return self._menu_principal(prefijo=prefijo)

    def _menu_principal(self, prefijo=''):
        texto = prefijo + f'Viaje #{self.despacho_id} — ¿en qué te ayudo?'
        return self._opts(texto, _menu_opciones())

    def _resumen(self):
        """Estado del viaje (solo lectura) y vuelve a ofrecer el menú."""
        r = _resumen_viaje(self.despacho_id)
        texto = (f'📦 Viaje #{self.despacho_id}\n'
                 f'• {r["total"]} guías en total\n'
                 f'• {r["entregadas"]} entregadas ✅\n'
                 f'• {r["novedad"]} con novedad ⚠️\n'
                 f'• {r["pendientes"]} pendientes ⏳')
        return self._opts(texto, _menu_opciones())

    def _ir_guias(self, prefijo=''):
        self.sesion.paso = RutAgenteSesion.PASO_GUIA
        return self._menu_guias(prefijo=prefijo)

    def _menu_guias(self, prefijo=''):
        guias = _guias_pendientes(self.despacho_id)
        if not guias:
            return self._cerrar(sin_novedades=True, prefijo='Ya no quedan guías pendientes. ')
        opciones = []
        for g in guias[:MAX_GUIAS_MENU]:
            titulo = f'{_etiqueta_guia(g)} · {(g.get("destinatario") or "").strip()}'.strip(' ·')
            opciones.append({'id': f'guia:{g["id"]}', 'titulo': titulo,
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
        texto = prefijo + f'Guía {guia.get("etiqueta", "")} · {guia.get("nombre", "")}. ¿Qué pasó?'
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
                  f'📦 Guía {guia.get("etiqueta", "")} · {guia.get("nombre", "")}',
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

    def _pide_humano(self, texto):
        t = (texto or '').lower()
        return any(w in t for w in _PIDE_HUMANO)

    def _pasar_a_humano(self, texto=MSJ_A_ASESOR):
        """Pausa el bot: la sesión pasa a modo HUMANO (la atiende un asesor por el
        inbox). El orquestador persiste el estado."""
        self.sesion.estado = RutAgenteSesion.ESTADO_HUMANO
        return {'tipo': 'texto', 'texto': texto}

    def _opts(self, texto, opciones, boton='Elegir'):
        """Arma la respuesta interactiva: botones si son <=3, lista si son más."""
        tipo = 'botones' if len(opciones) <= 3 else 'lista'
        return {'tipo': tipo, 'texto': texto[:1024], 'opciones': opciones, 'boton': boton}

    # -- matching de texto libre -------------------------------------------
    def _buscar_guia(self, vid):
        """Busca la guía pendiente por su id interno."""
        try:
            vid = int(vid)
        except (TypeError, ValueError):
            return None
        for g in _guias_pendientes(self.despacho_id):
            if g['id'] == vid:
                return g
        return None

    def _match_guia(self, texto):
        """Match de texto libre a una guía pendiente, por número exacto o por nombre."""
        t = (texto or '').strip().lower()
        if not t:
            return None
        guias = _guias_pendientes(self.despacho_id)
        digitos = re.sub(r'\D', '', t)
        if digitos:
            for g in guias:
                if str(g.get('numero') or '') == digitos:
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
def _marcar_apoyo(telefono, requiere):
    """Prende/apaga la marca 'requiere apoyo' de la conversación del inbox, para que
    el asesor la vea resaltada cuando LOGY pasa a modo humano."""
    try:
        from mensajeria.models import MsjConversacion
        MsjConversacion.objects.filter(cliente_telefono=telefono).update(requiere_apoyo=requiere)
    except Exception:
        logger.exception('LOGY: no se pudo marcar apoyo=%s para %s', requiere, telefono)


def procesar_entrante_conductor(telefono, texto, conexion, opcion_id=None):
    """Orquesta un mensaje entrante del conductor.

    - Sesión ACTIVA para este teléfono -> corre la máquina de estados y responde.
    - Sin sesión -> intenta ARRANCAR por placa (self-service, con auth híbrida).
    - Nada matchea -> devuelve None (el mensaje sigue al inbox normal).

    `opcion_id` es el id del botón/fila que tocó el conductor (ej. 'guia:6733712');
    None si escribió texto. El schema del tenant ya viene seteado por el webhook.
    """
    from mensajeria.servicios.whatsapp_cliente import WhatsappCliente

    # Cierra sesiones abandonadas (sin actividad hace rato): no quedan colgadas
    # para siempre bloqueando el próximo viaje del mismo número. Aplica también al
    # modo humano (si el asesor no la cerró, expira sola).
    vivas = [RutAgenteSesion.ESTADO_ACTIVA, RutAgenteSesion.ESTADO_HUMANO]
    limite = timezone.now() - timedelta(hours=HORAS_SESION_ACTIVA)
    RutAgenteSesion.objects.filter(
        telefono=telefono, estado__in=vivas, fecha_actualizacion__lt=limite,
    ).update(estado=RutAgenteSesion.ESTADO_CERRADA)

    sesion = (
        RutAgenteSesion.objects
        .filter(telefono=telefono, estado__in=vivas, fecha_actualizacion__gte=limite)
        .order_by('-id').first()
    )
    if sesion and sesion.estado == RutAgenteSesion.ESTADO_HUMANO:
        # Modo humano: el asesor atiende, el bot NO responde. El único que reactiva
        # al bot es la placa (el conductor terminó con el asesor y quiere seguir).
        despacho, _m = _resolver_o_diagnosticar(texto, telefono)
        if not despacho:
            return None   # el mensaje va al inbox; lo maneja el asesor
        sesion.estado = RutAgenteSesion.ESTADO_CERRADA
        sesion.save(update_fields=['estado', 'fecha_actualizacion'])
        _marcar_apoyo(telefono, False)   # vuelve el bot -> apagamos la marca
        sesion = None     # cae al arranque por placa abajo

    if not sesion:
        despacho, motivo = _resolver_o_diagnosticar(texto, telefono)
        # Sin placa en el texto: ¿el número ya está ligado a un viaje? -> arranca
        # directo (el conductor escribe "hola" y ve el menú, sin pedir la placa).
        if despacho is None and motivo is None and not opcion_id \
                and len((texto or '').split()) <= MAX_PALABRAS_PLACA:
            despacho = _despacho_por_telefono(telefono)
        if despacho:
            nueva, _envio = _arrancar_sesion(conexion, despacho.id, telefono, _nombre_conductor(despacho))
            if not nueva:
                return None
            return nueva.historial[-1]['texto'] if nueva.historial else ''
        if motivo:
            # Había una placa que no sirve (inexistente/vieja/sin aprobar/de otro
            # número): mensaje ESPECÍFICO, no la bienvenida genérica.
            return _enviar_texto_suelto(conexion, telefono, motivo)
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
        # El flujo explotó: en vez de dejar al conductor en un dead-end, ESCALA a un
        # asesor humano (la sesión pasa a modo humano y sigue por el inbox).
        logger.exception('LOGY: el flujo falló para %s (despacho %s)', telefono, sesion.despacho_id)
        sesion.estado = RutAgenteSesion.ESTADO_HUMANO
        respuesta = {'tipo': 'texto', 'texto': MSJ_ERROR_A_ASESOR}

    sesion.contexto = flujo.ctx
    hist = list(sesion.historial or [])
    hist.append({'rol': 'usuario', 'texto': texto, 'opcion': opcion_id})
    hist.append({'rol': 'agente', 'texto': respuesta.get('texto', '')})
    sesion.historial = hist[-40:]   # transcripción acotada
    sesion.save(update_fields=['paso', 'contexto', 'estado', 'historial', 'fecha_actualizacion'])

    if sesion.estado == RutAgenteSesion.ESTADO_HUMANO:
        # LOGY pasó a un asesor: resaltamos la conversación en el inbox.
        _marcar_apoyo(telefono, True)

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


def _resolver_o_diagnosticar(texto, telefono):
    """Para un texto sin sesión, intenta resolver la placa a un despacho para
    arrancar. Devuelve:
      - (despacho, None)  -> arranca.
      - (None, motivo)    -> hay una placa que NO sirve; `motivo` es el mensaje
                             específico para el conductor (inexistente / vieja /
                             sin aprobar / de otro número).
      - (None, None)      -> no hay placa (mensaje corto -> bienvenida; largo -> inbox).

    Solo diagnostica mensajes cortos, para no secuestrar mensajes largos de clientes.
    """
    from ruteo.models.despacho import RutDespacho

    if len((texto or '').split()) > MAX_PALABRAS_PLACA:
        return None, None
    placas = _extraer_placas(texto)
    if not placas:
        return None, None
    limite = timezone.now() - timedelta(days=DIAS_VENTANA_PLACA)
    for placa in placas:
        despacho = (
            RutDespacho.objects
            .filter(vehiculo__placa__iexact=placa, estado_anulado=False)
            .order_by('-id').first()
        )
        if not despacho:
            continue
        if not despacho.estado_aprobado:
            return None, (f'El viaje de la placa {placa} todavía no está listo (sin aprobar). '
                          f'Avisá al despachador. 🙏')
        if despacho.fecha and despacho.fecha < limite:
            return None, (f'El viaje de la placa {placa} es de hace más de {DIAS_VENTANA_PLACA} días, '
                          f'no lo puedo cerrar por acá. Si es un viaje nuevo, avisá al despachador. 🙏')
        esperado = _telefono_esperado(despacho)
        if esperado and not _mismo_numero(esperado, telefono):
            logger.warning('LOGY: %s escribió la placa del viaje %s pero no es el número autorizado.',
                           telefono, despacho.id)
            return None, (f'El viaje de la placa {placa} está registrado a otro número. '
                          f'Si sos vos, pedile al despachador que actualice tu teléfono. 🙏')
        return despacho, None
    return None, (f'No encontré ningún viaje con la placa {placas[0]}. '
                  f'Revisá que esté bien escrita, o avisá al despachador. 🙏')


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


def _despacho_por_telefono(telefono):
    """Despacho activo reciente cuyo número autorizado coincide con `telefono`.

    Permite que el conductor arranque LOGY escribiendo cualquier cosa ("hola") sin
    la placa: si su número ya está ligado a un viaje (lo registró el despachador, o
    es el conductor asignado), se resuelve solo. Devuelve el más reciente o None.
    """
    from django.db.models import Q
    from ruteo.models.despacho import RutDespacho

    last10 = re.sub(r'\D', '', str(telefono or ''))[-10:]
    if len(last10) != 10:
        return None
    limite = timezone.now() - timedelta(days=DIAS_VENTANA_PLACA)
    base = RutDespacho.objects.filter(
        Q(fecha__gte=limite) | Q(fecha__isnull=True),
        estado_aprobado=True, estado_anulado=False)
    # 1) por teléfono registrado (lo carga "Consultar al conductor") — consulta directa.
    d = base.filter(conductor_telefono__endswith=last10).order_by('-id').first()
    if d:
        return d
    # 2) por conductor asignado (su teléfono vive en User, otro schema).
    for d in base.filter(conductor_id__isnull=False).order_by('-id')[:30]:
        if _mismo_numero(_telefono_esperado(d), telefono):
            return d
    return None


def _nombre_conductor(despacho):
    """Nombre del conductor asignado al despacho (si hay); si no, 'conductor'."""
    from contenedor.models import User
    user = User.objects.filter(pk=despacho.conductor_id).first() if despacho.conductor_id else None
    nombre = f"{(user.nombre or '')} {(user.apellido or '')}".strip() if user else ''
    return nombre or 'conductor'


def _enviar_texto_suelto(conexion, telefono, texto):
    """Manda un texto suelto (bienvenida o diagnóstico de placa). Devuelve el texto,
    o None si no se pudo enviar."""
    from mensajeria.servicios.whatsapp_cliente import WhatsappCliente
    try:
        envio = WhatsappCliente(conexion).enviar_texto(telefono, texto)
    except Exception:
        logger.exception('LOGY: fallo enviando texto suelto a %s', telefono)
        return None
    if isinstance(envio, dict) and envio.get('error'):
        logger.error('LOGY: Meta rechazó el texto a %s: %s', telefono, envio.get('mensaje'))
        return None
    return texto


def _bienvenida(conexion, telefono):
    """Saluda a un texto corto sin sesión y le pide la placa (no crea sesión: la
    placa es la que arranca el flujo). Así el conductor que escribe suelto no queda
    sin respuesta."""
    empresa = getattr(getattr(conexion, 'contenedor', None), 'nombre', None) or 'la empresa'
    saludo = (
        f'¡Hola! 👋 Soy {NOMBRE_AGENTE}, el asistente de {empresa}. '
        f'Para cerrar tu viaje y reportar novedades, escribime tu *placa* (ej. ABC123).'
    )
    return _enviar_texto_suelto(conexion, telefono, saludo)


def _arrancar_sesion(conexion, despacho_id, telefono, conductor_nombre):
    """Manda el saludo + menú principal con botones y, si Meta lo acepta, crea la
    sesión ACTIVA en paso 'menu'. Devuelve (sesion, envio); sesion=None si el envío
    falló, para no dejar sesión fantasma."""
    from mensajeria.servicios.whatsapp_cliente import WhatsappCliente

    empresa = getattr(getattr(conexion, 'contenedor', None), 'nombre', None) or 'la empresa'
    saludo = (
        f'¡Hola {conductor_nombre}! 👋 Soy {NOMBRE_AGENTE}, el asistente de {empresa}. '
        f'Viaje #{despacho_id} — ¿en qué te ayudo?'
    )
    try:
        envio = WhatsappCliente(conexion).enviar_botones(telefono, saludo, _menu_opciones())
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
