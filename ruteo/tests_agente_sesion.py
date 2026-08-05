"""Tests del orquestador de sesion (webhook -> agente -> WhatsApp).

LLM con guion fijo + WhatsappCliente mockeado (en su ORIGEN, porque se importa
local dentro de la funcion). Verifica que un entrante del conductor con sesion
activa corre el agente, registra la novedad, responde por WhatsApp y persiste el
historial para poder RETOMAR en el proximo mensaje.

Correr: python manage.py test ruteo.tests_agente_sesion
"""
from unittest.mock import patch

from django_tenants.test.cases import TenantTestCase

from ruteo.models.agente_sesion import RutAgenteSesion
from ruteo.models.despacho import RutDespacho
from ruteo.models.novedad import RutNovedad
from ruteo.models.novedad_tipo import RutNovedadTipo
from ruteo.models.vehiculo import RutVehiculo
from ruteo.models.visita import RutVisita
from ruteo.servicios.agente_conductor import procesar_entrante_conductor
from ruteo.tests_agente_conductor import LLMFalso

TEL = '573001112233'


class _Contenedor:
    nombre = 'Energy'
    schema_name = 'test'


class _Conexion:
    contenedor = _Contenedor()


class OrquestadorSesionTests(TenantTestCase):

    def setUp(self):
        super().setUp()
        RutNovedadTipo.objects.create(id=1, nombre='Cliente ausente')
        self.vehiculo = RutVehiculo.objects.create(placa='ABC123', estado_asignado=True)
        self.despacho = RutDespacho.objects.create(estado_aprobado=True, vehiculo=self.vehiculo)
        self.v2 = RutVisita.objects.create(
            despacho=self.despacho, ciudad_id=None, numero='200002',
            destinatario='Ana', destinatario_direccion='Cra 2',
        )

    def _sesion(self, historial=None):
        return RutAgenteSesion.objects.create(
            despacho=self.despacho, telefono=TEL, conductor_nombre='Pedro',
            estado=RutAgenteSesion.ESTADO_ACTIVA, historial=historial or [],
        )

    @patch('movil.services.novedad._notificar')
    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_entrante_con_sesion_corre_agente_y_responde(self, WC, _notif):
        sesion = self._sesion()
        guion = [
            {'texto': None, 'tool_calls': [{'nombre': 'guias_pendientes', 'args': {}}]},
            {'texto': None, 'tool_calls': [{'nombre': 'registrar_novedad',
                'args': {'guia_numero': '200002', 'novedad_tipo_id': 1, 'motivo': 'no estaba'}}]},
            {'texto': 'Listo, registré la novedad de la 200002.', 'tool_calls': []},
        ]
        respuesta = procesar_entrante_conductor(TEL, 'la de ana no estaba', _Conexion(), cliente_llm=LLMFalso(guion))

        self.assertIn('200002', respuesta)
        self.assertEqual(RutNovedad.objects.filter(visita=self.v2).count(), 1)
        WC.return_value.enviar_texto.assert_called_once()
        tel_arg, texto_arg = WC.return_value.enviar_texto.call_args.args
        self.assertEqual(tel_arg, TEL)
        self.assertIn('200002', texto_arg)
        sesion.refresh_from_db()
        self.assertGreater(len(sesion.historial), 1)  # historial persistido para retomar

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_sin_sesion_devuelve_none(self, WC):
        respuesta = procesar_entrante_conductor('599999999', 'hola', _Conexion(), cliente_llm=LLMFalso([]))
        self.assertIsNone(respuesta)
        WC.return_value.enviar_texto.assert_not_called()

    @patch('movil.services.novedad._notificar')
    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_retoma_historial_previo(self, WC, _notif):
        previo = [
            {'rol': 'usuario', 'texto': 'hola'},
            {'rol': 'agente', 'texto': '¿en qué guías tuviste problema?'},
        ]
        sesion = self._sesion(historial=previo)
        procesar_entrante_conductor(
            TEL, 'ninguna, todo bien', _Conexion(),
            cliente_llm=LLMFalso([{'texto': 'Ok, gracias.', 'tool_calls': []}]),
        )
        sesion.refresh_from_db()
        # previo(2) + usuario nuevo(1) + agente(1) = 4
        self.assertEqual(len(sesion.historial), 4)
        self.assertEqual(sesion.historial[2], {'rol': 'usuario', 'texto': 'ninguna, todo bien'})
