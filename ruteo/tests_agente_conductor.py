"""Tests del agente de conductores (piloto solo-novedades).

Usan un LLM con GUION FIJO (sin red ni API key) y las TOOLS REALES contra la BD
de test. Verifican que el agente:
  - registra la novedad de una guía que el conductor reporta,
  - no toca guías ajenas al viaje ni tipos inválidos (guardrails),
  - es idempotente (no duplica),
  - corta seguro si el modelo se cuelga pidiendo tools.

Correr: python manage.py test ruteo.tests_agente_conductor
"""
from unittest.mock import patch

from django_tenants.test.cases import TenantTestCase

from ruteo.models.despacho import RutDespacho
from ruteo.models.novedad import RutNovedad
from ruteo.models.novedad_tipo import RutNovedadTipo
from ruteo.models.vehiculo import RutVehiculo
from ruteo.models.visita import RutVisita
from ruteo.servicios.agente_conductor import AgenteConductor


class LLMFalso:
    """LLM con guion fijo: devuelve respuestas neutrales pre-programadas, en orden."""

    def __init__(self, guion):
        self.guion = list(guion)
        self.vistos = []

    def generar(self, system, mensajes, herramientas=None):
        self.vistos.append(list(mensajes))
        return self.guion.pop(0)


class _TenantStub:
    schema_name = 'test'


class AgenteConductorTests(TenantTestCase):

    def setUp(self):
        super().setUp()
        RutNovedadTipo.objects.create(id=1, nombre='Cliente ausente')
        RutNovedadTipo.objects.create(id=2, nombre='Dirección errada')
        self.vehiculo = RutVehiculo.objects.create(placa='ABC123', estado_asignado=True)
        self.despacho = RutDespacho.objects.create(estado_aprobado=True, vehiculo=self.vehiculo)
        self.v1 = RutVisita.objects.create(despacho=self.despacho, ciudad_id=None, numero='200001', destinatario='Luis', destinatario_direccion='Calle 1')
        self.v2 = RutVisita.objects.create(despacho=self.despacho, ciudad_id=None, numero='200002', destinatario='Ana', destinatario_direccion='Cra 2')
        self.v3 = RutVisita.objects.create(despacho=self.despacho, ciudad_id=None, numero='200003', destinatario='Juan', destinatario_direccion='Av 3')

    def _agente(self, guion):
        return AgenteConductor(
            self.despacho.id, _TenantStub(), cliente_llm=LLMFalso(guion),
            empresa='Energy', conductor='Pedro',
        )

    @patch('movil.services.novedad._notificar')
    def test_flujo_registra_novedad(self, _notif):
        guion = [
            {'texto': None, 'tool_calls': [{'nombre': 'guias_pendientes', 'args': {}}]},
            {'texto': None, 'tool_calls': [{'nombre': 'registrar_novedad',
                'args': {'guia_numero': '200002', 'novedad_tipo_id': 1, 'motivo': 'no estaba'}}]},
            {'texto': 'Listo, registré 1 novedad en la guía 200002.', 'tool_calls': []},
        ]
        agente = self._agente(guion)
        r = agente.paso([{'rol': 'usuario', 'texto': 'la de Ana no estaba'}])

        self.assertIn('200002', r['texto'])
        self.v2.refresh_from_db()
        self.assertTrue(self.v2.estado_novedad)
        novedades = RutNovedad.objects.filter(visita=self.v2)
        self.assertEqual(novedades.count(), 1)
        self.assertEqual(novedades.first().novedad_tipo_id, 1)
        self.assertEqual(novedades.first().descripcion, 'no estaba')
        self.assertEqual(len(agente.novedades_registradas), 1)

    def test_ofrecer_opciones_botones_cierra_turno(self):
        # <=3 opciones -> botones. Un solo item en el guion prueba que NO vuelve a
        # llamar al LLM: ofrecer_opciones cierra el turno esperando el toque.
        guion = [{'texto': None, 'tool_calls': [{'nombre': 'ofrecer_opciones', 'args': {
            'texto': '¿Qué guía tuvo novedad?',
            'opciones': [{'titulo': '200002 - Ana'}, {'titulo': '200003 - Juan'}],
        }}]}]
        agente = self._agente(guion)
        r = agente.paso([{'rol': 'usuario', 'texto': 'reportar novedad'}])
        self.assertEqual(r['tipo'], 'botones')
        self.assertEqual([o['titulo'] for o in r['opciones']], ['200002 - Ana', '200003 - Juan'])
        self.assertEqual(r['texto'], '¿Qué guía tuvo novedad?')
        # el tool_result quedó en el historial (para el siguiente turno)
        self.assertEqual(r['mensajes'][-1]['rol'], 'tool')

    def test_ofrecer_opciones_lista_cuando_muchas(self):
        # >3 opciones -> lista.
        opciones = [{'titulo': f'op {i}'} for i in range(5)]
        guion = [{'texto': None, 'tool_calls': [{'nombre': 'ofrecer_opciones',
            'args': {'texto': 'Elegí', 'opciones': opciones}}]}]
        agente = self._agente(guion)
        r = agente.paso([{'rol': 'usuario', 'texto': 'hola'}])
        self.assertEqual(r['tipo'], 'lista')
        self.assertEqual(len(r['opciones']), 5)

    def test_mismo_numero(self):
        from ruteo.servicios.agente_conductor import _mismo_numero
        self.assertTrue(_mismo_numero('573006134088', '3006134088'))       # con/sin prefijo país
        self.assertTrue(_mismo_numero('+57 300 613 4088', '573006134088')) # con formato
        self.assertFalse(_mismo_numero('573006134088', '573009999999'))    # distintos
        self.assertFalse(_mismo_numero('', '573006134088'))                # vacío
        self.assertFalse(_mismo_numero(None, None))

    def test_extraer_placas(self):
        from ruteo.servicios.agente_conductor import _extraer_placas
        self.assertEqual(_extraer_placas('ABC123'), ['ABC123'])
        self.assertEqual(_extraer_placas('hola ABC123'), ['ABC123'])
        self.assertEqual(_extraer_placas('abc-123'), ['ABC123'])         # minúsculas + guión
        self.assertEqual(_extraer_placas('ABC 123 listo'), ['ABC123'])   # espacio, sin comer 'listo'
        self.assertEqual(_extraer_placas('moto ABC12D'), ['ABC12D'])     # placa de moto
        self.assertEqual(_extraer_placas('hola buenas'), [])             # sin placa

    def test_ofrecer_opciones_tolera_strings_y_basura(self):
        # El modelo a veces manda opciones como strings sueltos, ints, o dicts sin
        # titulo. No debe crashear: se normaliza y se descarta lo inválido.
        agente = self._agente([])
        r = agente._construir_interactivo({
            'texto': 'Elegí', 'opciones': ['Ana', {'titulo': 'Juan'}, 42, {'x': 1}, {'titulo': '  '}],
        })
        self.assertEqual(r['tipo'], 'botones')
        self.assertEqual([o['titulo'] for o in r['opciones']], ['Ana', 'Juan', '42'])

    def test_ofrecer_opciones_sin_opciones_validas_cae_a_texto(self):
        agente = self._agente([])
        r = agente._construir_interactivo({'texto': 'Hola', 'opciones': []})
        self.assertEqual(r['tipo'], 'texto')
        self.assertEqual(r['texto'], 'Hola')
        # 'opciones' que no es lista tampoco tumba nada.
        r2 = agente._construir_interactivo({'opciones': 'no es lista'})
        self.assertEqual(r2['tipo'], 'texto')

    def test_ofrecer_opciones_recorta_a_10(self):
        agente = self._agente([])
        r = agente._construir_interactivo({'texto': 'x', 'opciones': [{'titulo': f'op{i}'} for i in range(15)]})
        self.assertEqual(r['tipo'], 'lista')
        self.assertEqual(len(r['opciones']), 10)  # límite de Meta

    def test_respuesta_vacia_del_modelo_cae_a_fallback(self):
        # Si el modelo responde texto vacío no mandamos un body vacío (Meta lo rechaza).
        agente = self._agente([{'texto': '', 'tool_calls': []}])
        r = agente.paso([{'rol': 'usuario', 'texto': 'hola'}])
        self.assertEqual(r['tipo'], 'texto')
        self.assertTrue(r['texto'].strip())

    @patch('movil.services.novedad._notificar')
    def test_guias_pendientes_solo_no_resueltas(self, _notif):
        self.v1.estado_entregado = True
        self.v1.save(update_fields=['estado_entregado'])
        agente = self._agente([])
        res = agente._t_guias_pendientes()
        self.assertEqual({g['guia'] for g in res['guias']}, {'200002', '200003'})
        self.assertEqual(res['total'], 2)

    def test_guia_ajena_no_registra(self):
        agente = self._agente([])
        res = agente._t_registrar_novedad({'guia_numero': '999999', 'novedad_tipo_id': 1, 'motivo': 'x'})
        self.assertFalse(res['ok'])
        self.assertEqual(RutNovedad.objects.count(), 0)

    def test_tipo_invalido_no_registra(self):
        agente = self._agente([])
        res = agente._t_registrar_novedad({'guia_numero': '200002', 'novedad_tipo_id': 999, 'motivo': 'x'})
        self.assertFalse(res['ok'])
        self.assertEqual(RutNovedad.objects.count(), 0)

    @patch('movil.services.novedad._notificar')
    def test_idempotente_no_duplica(self, _notif):
        agente = self._agente([])
        args = {'guia_numero': '200002', 'novedad_tipo_id': 1, 'motivo': 'no estaba'}
        agente._t_registrar_novedad(args)
        agente._t_registrar_novedad(args)  # mismo (despacho, guía, tipo) -> mismo movil_token
        self.assertEqual(RutNovedad.objects.filter(visita=self.v2).count(), 1)

    @patch('movil.services.novedad._notificar')
    def test_tope_de_rondas_cierra_seguro(self, _notif):
        # LLM que SIEMPRE pide una tool y nunca da texto -> debe cortar sin colgarse.
        guion = [{'texto': None, 'tool_calls': [{'nombre': 'tipos_novedad', 'args': {}}]}] * 10
        agente = self._agente(guion)
        r = agente.paso([{'rol': 'usuario', 'texto': 'hola'}])
        self.assertIn('compañero', r['texto'])
