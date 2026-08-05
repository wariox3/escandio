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


class _LLMExplota:
    """LLM que siempre falla (simula timeout/cuota/500 de la API)."""

    def generar(self, *a, **k):
        raise RuntimeError('boom red')


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
    def test_respuesta_interactiva_manda_botones(self, WC):
        # Si el agente ofrece opciones, el orquestador manda botones (no texto plano).
        self._sesion()
        guion = [{'texto': None, 'tool_calls': [{'nombre': 'ofrecer_opciones', 'args': {
            'texto': '¿Qué querés hacer?',
            'opciones': [{'titulo': 'Reportar novedad'}, {'titulo': 'Sin novedades'}],
        }}]}]
        procesar_entrante_conductor(TEL, 'hola', _Conexion(), cliente_llm=LLMFalso(guion))
        WC.return_value.enviar_botones.assert_called_once()
        WC.return_value.enviar_texto.assert_not_called()
        tel_arg, texto_arg, ops_arg = WC.return_value.enviar_botones.call_args.args
        self.assertEqual(tel_arg, TEL)
        self.assertEqual([o['titulo'] for o in ops_arg], ['Reportar novedad', 'Sin novedades'])

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_llm_falla_responde_fallback_y_no_pierde_turno(self, WC):
        # El LLM explota: el conductor igual recibe un fallback y su mensaje queda
        # guardado (para retomar), en vez de un silencio total.
        sesion = self._sesion()
        respuesta = procesar_entrante_conductor(TEL, 'hola', _Conexion(), cliente_llm=_LLMExplota())
        self.assertTrue(respuesta.strip())
        WC.return_value.enviar_texto.assert_called_once()  # fallback por texto plano
        sesion.refresh_from_db()
        self.assertEqual(sesion.historial[-2], {'rol': 'usuario', 'texto': 'hola'})
        self.assertEqual(sesion.historial[-1]['rol'], 'agente')

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_envio_rechazado_por_meta_no_crashea(self, WC):
        # Meta devuelve error (dict, no excepción): no debe romper el flujo.
        self._sesion()
        WC.return_value.enviar_texto.return_value = {'error': True, 'mensaje': 'fuera de ventana'}
        respuesta = procesar_entrante_conductor(
            TEL, 'todo bien', _Conexion(),
            cliente_llm=LLMFalso([{'texto': 'Listo, gracias.', 'tool_calls': []}]),
        )
        self.assertIn('Listo', respuesta)  # devolvió normal pese al error de envío

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_sin_sesion_devuelve_none(self, WC):
        respuesta = procesar_entrante_conductor('599999999', 'hola', _Conexion(), cliente_llm=LLMFalso([]))
        self.assertIsNone(respuesta)
        WC.return_value.enviar_texto.assert_not_called()

    # -- arranque self-service por placa (conductor sin sesión escribe su placa) --

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_placa_arranca_sesion_y_saluda(self, WC):
        tel = '573007654321'
        respuesta = procesar_entrante_conductor(tel, 'ABC123', _Conexion(), cliente_llm=LLMFalso([]))
        self.assertTrue(respuesta)  # devolvió el saludo
        ses = RutAgenteSesion.objects.filter(
            despacho=self.despacho, telefono=tel, estado=RutAgenteSesion.ESTADO_ACTIVA)
        self.assertEqual(ses.count(), 1)
        WC.return_value.enviar_botones.assert_called_once()
        _tel, _texto, opciones = WC.return_value.enviar_botones.call_args.args
        self.assertEqual([o['titulo'] for o in opciones], ['Reportar novedad', 'Sin novedades'])

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_mensaje_sin_placa_no_arranca(self, WC):
        respuesta = procesar_entrante_conductor('573007654321', 'hola buenas', _Conexion(), cliente_llm=LLMFalso([]))
        self.assertIsNone(respuesta)
        self.assertEqual(RutAgenteSesion.objects.count(), 0)
        WC.return_value.enviar_botones.assert_not_called()

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_placa_inexistente_no_arranca(self, WC):
        respuesta = procesar_entrante_conductor('573007654321', 'ZZZ999', _Conexion(), cliente_llm=LLMFalso([]))
        self.assertIsNone(respuesta)
        self.assertEqual(RutAgenteSesion.objects.count(), 0)

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_placa_de_despacho_anulado_no_arranca(self, WC):
        self.despacho.estado_anulado = True
        self.despacho.save(update_fields=['estado_anulado'])
        respuesta = procesar_entrante_conductor('573007654321', 'ABC123', _Conexion(), cliente_llm=LLMFalso([]))
        self.assertIsNone(respuesta)
        self.assertEqual(RutAgenteSesion.objects.count(), 0)

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_placa_de_numero_autorizado_arranca(self, WC):
        # El viaje tiene número autorizado y escribe ESE número -> arranca.
        self.despacho.conductor_telefono = '573007654321'
        self.despacho.save(update_fields=['conductor_telefono'])
        respuesta = procesar_entrante_conductor('573007654321', 'ABC123', _Conexion(), cliente_llm=LLMFalso([]))
        self.assertTrue(respuesta)
        self.assertEqual(RutAgenteSesion.objects.filter(despacho=self.despacho).count(), 1)
        WC.return_value.enviar_botones.assert_called_once()

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_placa_de_numero_no_autorizado_no_arranca(self, WC):
        # El viaje tiene número autorizado pero escribe OTRO -> no arranca (anti-abuso).
        self.despacho.conductor_telefono = '573007654321'
        self.despacho.save(update_fields=['conductor_telefono'])
        respuesta = procesar_entrante_conductor('573009999999', 'ABC123', _Conexion(), cliente_llm=LLMFalso([]))
        self.assertIsNone(respuesta)
        self.assertEqual(RutAgenteSesion.objects.count(), 0)
        WC.return_value.enviar_botones.assert_not_called()

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_mensaje_largo_con_placa_no_secuestra(self, WC):
        # Cliente que casualmente menciona una placa en un mensaje largo: NO arranca.
        largo = 'hola necesito ayuda con mi pedido de la placa ABC123 que no llegó gracias'
        respuesta = procesar_entrante_conductor('573007654321', largo, _Conexion(), cliente_llm=LLMFalso([]))
        self.assertIsNone(respuesta)
        self.assertEqual(RutAgenteSesion.objects.count(), 0)

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_placa_arranca_y_luego_conversa(self, WC):
        # 1) la placa arranca la sesión; 2) el siguiente mensaje ya corre el agente.
        tel = '573007654321'
        procesar_entrante_conductor(tel, 'ABC123', _Conexion(), cliente_llm=LLMFalso([]))
        procesar_entrante_conductor(
            tel, 'Sin novedades', _Conexion(),
            cliente_llm=LLMFalso([{'texto': 'Perfecto, gracias. Buen camino 🚚', 'tool_calls': []}]),
        )
        ses = RutAgenteSesion.objects.get(telefono=tel)
        # saludo + usuario('Sin novedades') + agente = 3
        self.assertGreaterEqual(len(ses.historial), 3)
        self.assertEqual(ses.historial[-1]['rol'], 'agente')

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
