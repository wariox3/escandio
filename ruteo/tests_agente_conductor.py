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
