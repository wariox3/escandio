"""Tests de LOGY: máquina de estados del flujo de novedades + helpers.

El flujo es DETERMINÍSTICO (sin LLM): se maneja por `opcion_id` (toque de botón,
ej. 'guia:200002') o por texto libre. Cada test corre transiciones reales contra
la BD de test.

Correr: python manage.py test ruteo.tests_agente_conductor
"""
from unittest.mock import patch

from django_tenants.test.cases import TenantTestCase

from ruteo.models.agente_sesion import RutAgenteSesion
from ruteo.models.despacho import RutDespacho
from ruteo.models.novedad import RutNovedad
from ruteo.models.novedad_tipo import RutNovedadTipo
from ruteo.models.vehiculo import RutVehiculo
from ruteo.models.visita import RutVisita
from ruteo.servicios.agente_conductor import FlujoNovedades, _registrar


class _TenantStub:
    schema_name = 'test'


class FlujoNovedadesTests(TenantTestCase):

    def setUp(self):
        super().setUp()
        RutNovedadTipo.objects.create(id=1, nombre='Cliente ausente')
        RutNovedadTipo.objects.create(id=2, nombre='Dirección errada')
        self.vehiculo = RutVehiculo.objects.create(placa='ABC123', estado_asignado=True)
        self.despacho = RutDespacho.objects.create(estado_aprobado=True, vehiculo=self.vehiculo)
        self.v1 = RutVisita.objects.create(despacho=self.despacho, ciudad_id=None, numero='200001', destinatario='Luis', destinatario_direccion='Calle 1')
        self.v2 = RutVisita.objects.create(despacho=self.despacho, ciudad_id=None, numero='200002', destinatario='Ana', destinatario_direccion='Cra 2')

    def _sesion(self, paso=RutAgenteSesion.PASO_MENU, contexto=None):
        return RutAgenteSesion.objects.create(
            despacho=self.despacho, telefono='573001112233', conductor_nombre='Pedro',
            estado=RutAgenteSesion.ESTADO_ACTIVA, paso=paso, contexto=contexto or {}, historial=[],
        )

    def _flujo(self, sesion):
        return FlujoNovedades(sesion, _TenantStub())

    def _ids(self, r):
        return [o['id'] for o in r.get('opciones', [])]

    # -- navegación principal ----------------------------------------------
    def test_menu_reportar_lleva_a_guias(self):
        ses = self._sesion()
        r = self._flujo(ses).procesar(None, 'menu:reportar')
        self.assertEqual(ses.paso, RutAgenteSesion.PASO_GUIA)
        self.assertIn('guia:200001', self._ids(r))
        self.assertIn('guia:200002', self._ids(r))
        self.assertIn('nav:volver', self._ids(r))

    def test_menu_guias_muestra_resumen_y_sigue_en_menu(self):
        self.v1.estado_entregado = True
        self.v1.save(update_fields=['estado_entregado'])
        ses = self._sesion()
        r = self._flujo(ses).procesar(None, 'menu:guias')
        self.assertIn('Viaje', r['texto'])
        self.assertIn('1 entregadas', r['texto'])
        self.assertIn('1 pendientes', r['texto'])
        self.assertEqual(ses.paso, RutAgenteSesion.PASO_MENU)   # solo lectura
        self.assertIn('menu:reportar', self._ids(r))            # re-ofrece el menú

    def test_menu_sin_novedades_cierra(self):
        ses = self._sesion()
        r = self._flujo(ses).procesar(None, 'menu:sin_novedades')
        self.assertEqual(r['tipo'], 'texto')
        self.assertEqual(ses.estado, RutAgenteSesion.ESTADO_CERRADA)
        self.assertIn('Sin novedades', r['texto'])

    def test_elegir_guia_lleva_a_tipos(self):
        ses = self._sesion(paso=RutAgenteSesion.PASO_GUIA)
        f = self._flujo(ses)
        r = f.procesar(None, 'guia:200002')
        self.assertEqual(ses.paso, RutAgenteSesion.PASO_TIPO)
        self.assertEqual(f.ctx['guia']['numero'], '200002')
        self.assertIn('tipo:1', self._ids(r))
        self.assertIn('nav:volver', self._ids(r))

    def test_elegir_tipo_pide_motivo(self):
        ses = self._sesion(paso=RutAgenteSesion.PASO_TIPO, contexto={'guia': {'numero': '200002', 'nombre': 'Ana'}})
        f = self._flujo(ses)
        r = f.procesar(None, 'tipo:1')
        self.assertEqual(ses.paso, RutAgenteSesion.PASO_MOTIVO)
        self.assertEqual(f.ctx['tipo']['id'], 1)
        self.assertIn('nav:omitir', self._ids(r))

    def test_motivo_lleva_a_confirmar(self):
        ses = self._sesion(paso=RutAgenteSesion.PASO_MOTIVO,
                           contexto={'guia': {'numero': '200002', 'nombre': 'Ana'}, 'tipo': {'id': 1, 'nombre': 'Cliente ausente'}})
        f = self._flujo(ses)
        r = f.procesar('no había nadie', None)
        self.assertEqual(ses.paso, RutAgenteSesion.PASO_CONFIRMA)
        self.assertEqual(f.ctx['motivo'], 'no había nadie')
        self.assertIn('Confirmá', r['texto'])
        self.assertIn('no había nadie', r['texto'])
        self.assertIn('conf:si', self._ids(r))

    def test_omitir_motivo_va_a_confirmar_sin_texto(self):
        ses = self._sesion(paso=RutAgenteSesion.PASO_MOTIVO,
                           contexto={'guia': {'numero': '200002', 'nombre': 'Ana'}, 'tipo': {'id': 1, 'nombre': 'Cliente ausente'}})
        f = self._flujo(ses)
        f.procesar(None, 'nav:omitir')
        self.assertEqual(ses.paso, RutAgenteSesion.PASO_CONFIRMA)
        self.assertEqual(f.ctx['motivo'], '')

    # -- registro (confirmación) -------------------------------------------
    @patch('movil.services.novedad._notificar')
    def test_confirmar_registra_la_novedad(self, _notif):
        ses = self._sesion(paso=RutAgenteSesion.PASO_CONFIRMA,
                           contexto={'guia': {'numero': '200002', 'nombre': 'Ana'}, 'tipo': {'id': 1, 'nombre': 'Cliente ausente'}, 'motivo': 'no estaba'})
        f = self._flujo(ses)
        r = f.procesar(None, 'conf:si')
        self.v2.refresh_from_db()
        self.assertTrue(self.v2.estado_novedad)
        nov = RutNovedad.objects.filter(visita=self.v2)
        self.assertEqual(nov.count(), 1)
        self.assertEqual(nov.first().novedad_tipo_id, 1)
        self.assertEqual(nov.first().descripcion, 'no estaba')
        self.assertEqual(ses.paso, RutAgenteSesion.PASO_OTRA)
        self.assertIn('✅', r['texto'])
        self.assertIn('200002', f.ctx['registradas'])

    def test_descartar_no_registra(self):
        ses = self._sesion(paso=RutAgenteSesion.PASO_CONFIRMA,
                           contexto={'guia': {'numero': '200002', 'nombre': 'Ana'}, 'tipo': {'id': 1, 'nombre': 'x'}, 'motivo': 'y'})
        f = self._flujo(ses)
        f.procesar(None, 'conf:descartar')
        self.assertEqual(RutNovedad.objects.count(), 0)
        self.assertEqual(ses.paso, RutAgenteSesion.PASO_GUIA)
        self.assertNotIn('guia', f.ctx)

    # -- navegación de retroceso / escape ----------------------------------
    def test_volver_desde_tipo_vuelve_a_guias(self):
        ses = self._sesion(paso=RutAgenteSesion.PASO_TIPO, contexto={'guia': {'numero': '200002', 'nombre': 'Ana'}})
        r = self._flujo(ses).procesar(None, 'nav:volver')
        self.assertEqual(ses.paso, RutAgenteSesion.PASO_GUIA)
        self.assertIn('guia:200002', self._ids(r))

    def test_volver_desde_guia_vuelve_a_menu(self):
        ses = self._sesion(paso=RutAgenteSesion.PASO_GUIA)
        r = self._flujo(ses).procesar(None, 'nav:volver')
        self.assertEqual(ses.paso, RutAgenteSesion.PASO_MENU)
        self.assertIn('menu:reportar', self._ids(r))

    def test_cancelar_global_limpia_y_va_a_menu(self):
        ses = self._sesion(paso=RutAgenteSesion.PASO_CONFIRMA,
                           contexto={'guia': {'numero': '200002'}, 'tipo': {'id': 1}})
        f = self._flujo(ses)
        f.procesar('cancelar', None)
        self.assertEqual(ses.paso, RutAgenteSesion.PASO_MENU)
        self.assertNotIn('guia', f.ctx)

    def test_texto_inesperado_nunca_queda_en_silencio(self):
        # El bug del "hola": cualquier cosa rara re-muestra el paso actual.
        ses = self._sesion(paso=RutAgenteSesion.PASO_MENU)
        r = self._flujo(ses).procesar('asdf qwer zxcv', None)
        self.assertTrue(r.get('texto'))
        self.assertIn('menu:reportar', self._ids(r))

    # -- match de texto libre ----------------------------------------------
    def test_match_guia_por_nombre(self):
        ses = self._sesion(paso=RutAgenteSesion.PASO_GUIA)
        f = self._flujo(ses)
        f.procesar('la de ana', None)
        self.assertEqual(ses.paso, RutAgenteSesion.PASO_TIPO)
        self.assertEqual(f.ctx['guia']['numero'], '200002')

    def test_match_guia_por_numero_escrito(self):
        ses = self._sesion(paso=RutAgenteSesion.PASO_GUIA)
        f = self._flujo(ses)
        f.procesar('200001', None)
        self.assertEqual(ses.paso, RutAgenteSesion.PASO_TIPO)
        self.assertEqual(f.ctx['guia']['numero'], '200001')

    def test_otra_si_vuelve_a_guias_y_no_cierra(self):
        ses = self._sesion(paso=RutAgenteSesion.PASO_OTRA)
        r = self._flujo(ses).procesar(None, 'otra:si')
        self.assertEqual(ses.paso, RutAgenteSesion.PASO_GUIA)
        ses2 = self._sesion(paso=RutAgenteSesion.PASO_OTRA)
        self._flujo(ses2).procesar(None, 'otra:no')
        self.assertEqual(ses2.estado, RutAgenteSesion.ESTADO_CERRADA)

    def test_guias_pendientes_excluye_resueltas(self):
        self.v1.estado_entregado = True
        self.v1.save(update_fields=['estado_entregado'])
        ses = self._sesion(paso=RutAgenteSesion.PASO_GUIA)
        r = self._flujo(ses).procesar(None, 'nav:menu')  # ir a menú y volver
        r = self._flujo(ses).procesar(None, 'menu:reportar')
        ids = self._ids(r)
        self.assertIn('guia:200002', ids)
        self.assertNotIn('guia:200001', ids)  # entregada -> no se ofrece

    # -- registro directo: guardrails + idempotencia -----------------------
    def test_guia_ajena_no_registra(self):
        ok, _ = _registrar(self.despacho.id, '999999', 1, 'x', _TenantStub())
        self.assertFalse(ok)
        self.assertEqual(RutNovedad.objects.count(), 0)

    def test_tipo_invalido_no_registra(self):
        ok, _ = _registrar(self.despacho.id, '200002', 999, 'x', _TenantStub())
        self.assertFalse(ok)
        self.assertEqual(RutNovedad.objects.count(), 0)

    @patch('movil.services.novedad._notificar')
    def test_registrar_idempotente(self, _notif):
        _registrar(self.despacho.id, '200002', 1, 'no estaba', _TenantStub())
        _registrar(self.despacho.id, '200002', 1, 'no estaba', _TenantStub())  # mismo token
        self.assertEqual(RutNovedad.objects.filter(visita=self.v2).count(), 1)


class HelpersTests(TenantTestCase):

    def test_mismo_numero(self):
        from ruteo.servicios.agente_conductor import _mismo_numero
        self.assertTrue(_mismo_numero('573006134088', '3006134088'))
        self.assertTrue(_mismo_numero('+57 300 613 4088', '573006134088'))
        self.assertFalse(_mismo_numero('573006134088', '573009999999'))
        self.assertFalse(_mismo_numero('', '573006134088'))
        self.assertFalse(_mismo_numero(None, None))

    def test_extraer_placas(self):
        from ruteo.servicios.agente_conductor import _extraer_placas
        self.assertEqual(_extraer_placas('ABC123'), ['ABC123'])
        self.assertEqual(_extraer_placas('hola ABC123'), ['ABC123'])
        self.assertEqual(_extraer_placas('abc-123'), ['ABC123'])
        self.assertEqual(_extraer_placas('ABC 123 listo'), ['ABC123'])
        self.assertEqual(_extraer_placas('moto ABC12D'), ['ABC12D'])
        self.assertEqual(_extraer_placas('hola buenas'), [])
