"""Tests del orquestador (webhook -> flujo -> WhatsApp).

Verifica el ruteo por sesión: arranque por placa (con auth híbrida y expiración),
y que un toque de botón corre la máquina de estados, persiste el estado y responde
por WhatsApp. Determinístico: sin LLM. WhatsappCliente se mockea en su origen
(se importa local dentro de la función).

Correr: python manage.py test ruteo.tests_agente_sesion
"""
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from django_tenants.test.cases import TenantTestCase

from ruteo.models.agente_sesion import RutAgenteSesion
from ruteo.models.despacho import RutDespacho
from ruteo.models.novedad import RutNovedad
from ruteo.models.novedad_tipo import RutNovedadTipo
from ruteo.models.vehiculo import RutVehiculo
from ruteo.models.visita import RutVisita
from ruteo.servicios.agente_conductor import procesar_entrante_conductor

TEL = '573001112233'


class _Contenedor:
    nombre = 'Energy'
    schema_name = 'test'


class _Conexion:
    contenedor = _Contenedor()


class OrquestadorTests(TenantTestCase):

    def setUp(self):
        super().setUp()
        RutNovedadTipo.objects.create(id=1, nombre='Cliente ausente')
        self.vehiculo = RutVehiculo.objects.create(placa='ABC123', estado_asignado=True)
        self.despacho = RutDespacho.objects.create(estado_aprobado=True, vehiculo=self.vehiculo)
        self.v2 = RutVisita.objects.create(despacho=self.despacho, ciudad_id=None, numero='200002',
                                           destinatario='Ana', destinatario_direccion='Cra 2')

    def _sesion(self, paso=RutAgenteSesion.PASO_MENU, contexto=None):
        return RutAgenteSesion.objects.create(
            despacho=self.despacho, telefono=TEL, conductor_nombre='Pedro',
            estado=RutAgenteSesion.ESTADO_ACTIVA, paso=paso, contexto=contexto or {}, historial=[],
        )

    # -- ruteo básico -------------------------------------------------------
    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_toque_boton_corre_flujo_y_persiste(self, WC):
        ses = self._sesion()
        procesar_entrante_conductor(TEL, '📋 Reportar novedad', _Conexion(), opcion_id='menu:reportar')
        ses.refresh_from_db()
        self.assertEqual(ses.paso, RutAgenteSesion.PASO_GUIA)   # avanzó de estado
        self.assertTrue(WC.return_value.enviar_botones.called or WC.return_value.enviar_lista.called)

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_texto_corto_sin_sesion_da_bienvenida(self, WC):
        # "hola" de un número DESCONOCIDO: LOGY saluda y pide la placa (no lo deja mudo).
        r = procesar_entrante_conductor('599999999', 'hola', _Conexion())
        self.assertTrue(r)
        self.assertIn('placa', r.lower())
        WC.return_value.enviar_texto.assert_called_once()
        self.assertEqual(RutAgenteSesion.objects.count(), 0)  # la sesión la crea la placa

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_hola_con_numero_registrado_arranca_sin_placa(self, WC):
        # El número YA está ligado al viaje -> "hola" abre el menú directo, sin placa.
        self.despacho.conductor_telefono = '573006134088'
        self.despacho.save(update_fields=['conductor_telefono'])
        r = procesar_entrante_conductor('573006134088', 'buenas', _Conexion())
        self.assertTrue(r)
        ses = RutAgenteSesion.objects.filter(telefono='573006134088', estado=RutAgenteSesion.ESTADO_ACTIVA)
        self.assertEqual(ses.count(), 1)
        WC.return_value.enviar_botones.assert_called_once()   # menú con opciones
        WC.return_value.enviar_texto.assert_not_called()      # no la bienvenida de texto

    # -- flujo completo -----------------------------------------------------
    @patch('movil.services.novedad._notificar')
    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_flujo_completo_registra_novedad(self, _WC, _notif):
        self._sesion()
        procesar_entrante_conductor(TEL, 'Reportar', _Conexion(), opcion_id='menu:reportar')
        procesar_entrante_conductor(TEL, '200002 · Ana', _Conexion(), opcion_id=f'guia:{self.v2.id}')
        procesar_entrante_conductor(TEL, 'Cliente ausente', _Conexion(), opcion_id='tipo:1')
        procesar_entrante_conductor(TEL, 'no estaba', _Conexion())          # motivo libre
        procesar_entrante_conductor(TEL, 'Confirmar', _Conexion(), opcion_id='conf:si')

        self.assertEqual(RutNovedad.objects.filter(visita=self.v2).count(), 1)
        ses = RutAgenteSesion.objects.get(telefono=TEL)
        self.assertEqual(ses.paso, RutAgenteSesion.PASO_OTRA)
        self.assertIn('200002', ses.contexto.get('registradas', []))

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_sin_novedades_cierra_sesion(self, _WC):
        self._sesion()
        procesar_entrante_conductor(TEL, 'Sin novedades', _Conexion(), opcion_id='menu:sin_novedades')
        ses = RutAgenteSesion.objects.get(telefono=TEL)
        self.assertEqual(ses.estado, RutAgenteSesion.ESTADO_CERRADA)

    # -- arranque por placa -------------------------------------------------
    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_placa_arranca_sesion_con_menu(self, WC):
        r = procesar_entrante_conductor('573007654321', 'ABC123', _Conexion())
        self.assertTrue(r)
        ses = RutAgenteSesion.objects.filter(telefono='573007654321', estado=RutAgenteSesion.ESTADO_ACTIVA)
        self.assertEqual(ses.count(), 1)
        self.assertEqual(ses.first().paso, RutAgenteSesion.PASO_MENU)
        WC.return_value.enviar_botones.assert_called_once()
        _tel, _texto, opciones = WC.return_value.enviar_botones.call_args.args
        self.assertEqual([o['id'] for o in opciones], ['menu:guias', 'menu:reportar', 'menu:sin_novedades'])

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_texto_largo_sin_placa_no_saluda(self, WC):
        # Un mensaje largo (probable cliente) NO se auto-responde: va al inbox humano.
        largo = 'buenas necesito saber donde esta mi pedido que pedí la semana pasada gracias'
        r = procesar_entrante_conductor('573007654321', largo, _Conexion())
        self.assertIsNone(r)
        WC.return_value.enviar_texto.assert_not_called()

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_mensaje_largo_con_placa_no_secuestra(self, _WC):
        largo = 'hola necesito ayuda con mi pedido de la placa ABC123 que no llegó gracias'
        r = procesar_entrante_conductor('573007654321', largo, _Conexion())
        self.assertIsNone(r)
        self.assertEqual(RutAgenteSesion.objects.count(), 0)

    # -- autorización híbrida ----------------------------------------------
    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_placa_numero_autorizado_arranca(self, _WC):
        self.despacho.conductor_telefono = '573007654321'
        self.despacho.save(update_fields=['conductor_telefono'])
        r = procesar_entrante_conductor('573007654321', 'ABC123', _Conexion())
        self.assertTrue(r)
        self.assertEqual(RutAgenteSesion.objects.filter(despacho=self.despacho).count(), 1)

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_placa_numero_no_autorizado_avisa_y_no_arranca(self, WC):
        self.despacho.conductor_telefono = '573007654321'
        self.despacho.save(update_fields=['conductor_telefono'])
        r = procesar_entrante_conductor('573009999999', 'ABC123', _Conexion())
        self.assertIn('otro número', r)                       # motivo específico, no silencio
        self.assertEqual(RutAgenteSesion.objects.count(), 0)  # no arranca
        WC.return_value.enviar_botones.assert_not_called()
        WC.return_value.enviar_texto.assert_called_once()     # avisa por texto

    # -- diagnóstico de placa que no sirve (no la bienvenida genérica) ------
    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_placa_inexistente_avisa(self, WC):
        r = procesar_entrante_conductor('573007654321', 'XYZ999', _Conexion())
        self.assertIn('No encontré', r)
        WC.return_value.enviar_texto.assert_called_once()
        self.assertEqual(RutAgenteSesion.objects.count(), 0)

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_placa_vieja_avisa(self, WC):
        self.despacho.fecha = timezone.now() - timedelta(days=30)
        self.despacho.save(update_fields=['fecha'])
        r = procesar_entrante_conductor('573007654321', 'ABC123', _Conexion())
        self.assertIn('días', r)
        WC.return_value.enviar_texto.assert_called_once()
        self.assertEqual(RutAgenteSesion.objects.count(), 0)

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_placa_sin_aprobar_avisa(self, WC):
        self.despacho.estado_aprobado = False
        self.despacho.save(update_fields=['estado_aprobado'])
        r = procesar_entrante_conductor('573007654321', 'ABC123', _Conexion())
        self.assertIn('aprobar', r)
        WC.return_value.enviar_texto.assert_called_once()
        self.assertEqual(RutAgenteSesion.objects.count(), 0)

    # -- expiración de sesión ----------------------------------------------
    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_sesion_vieja_se_cierra_sola(self, _WC):
        ses = self._sesion()
        RutAgenteSesion.objects.filter(pk=ses.id).update(fecha_actualizacion=timezone.now() - timedelta(hours=24))
        procesar_entrante_conductor(TEL, 'hola', _Conexion())   # sin placa (texto corto)
        ses.refresh_from_db()
        self.assertEqual(ses.estado, RutAgenteSesion.ESTADO_CERRADA)   # la vieja quedó cerrada

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_placa_arranca_aunque_haya_sesion_vieja(self, _WC):
        vieja = self._sesion()
        RutAgenteSesion.objects.filter(pk=vieja.id).update(fecha_actualizacion=timezone.now() - timedelta(hours=24))
        r = procesar_entrante_conductor(TEL, 'ABC123', _Conexion())
        self.assertTrue(r)
        vieja.refresh_from_db()
        self.assertEqual(vieja.estado, RutAgenteSesion.ESTADO_CERRADA)
        activas = RutAgenteSesion.objects.filter(telefono=TEL, estado=RutAgenteSesion.ESTADO_ACTIVA)
        self.assertEqual(activas.count(), 1)

    # -- handoff a asesor humano -------------------------------------------
    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_pedir_asesor_pausa_el_bot(self, _WC):
        self._sesion()
        procesar_entrante_conductor(TEL, 'quiero hablar con un asesor', _Conexion())
        ses = RutAgenteSesion.objects.get(telefono=TEL)
        self.assertEqual(ses.estado, RutAgenteSesion.ESTADO_HUMANO)
        # el bot ya no responde: lo atiende el asesor por el inbox
        r = procesar_entrante_conductor(TEL, 'sigo esperando', _Conexion())
        self.assertIsNone(r)

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_placa_reactiva_el_bot_desde_humano(self, _WC):
        s = self._sesion()
        RutAgenteSesion.objects.filter(pk=s.id).update(estado=RutAgenteSesion.ESTADO_HUMANO)
        r = procesar_entrante_conductor(TEL, 'ABC123', _Conexion())
        self.assertTrue(r)                                            # la placa reactiva el bot
        s.refresh_from_db()
        self.assertEqual(s.estado, RutAgenteSesion.ESTADO_CERRADA)    # la humana se cerró
        self.assertEqual(RutAgenteSesion.objects.filter(
            telefono=TEL, estado=RutAgenteSesion.ESTADO_ACTIVA).count(), 1)

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    def test_error_del_flujo_escala_a_asesor(self, WC):
        self._sesion()
        with patch('ruteo.servicios.agente_conductor.FlujoNovedades.procesar', side_effect=RuntimeError('boom')):
            procesar_entrante_conductor(TEL, 'hola', _Conexion())
        ses = RutAgenteSesion.objects.get(telefono=TEL)
        self.assertEqual(ses.estado, RutAgenteSesion.ESTADO_HUMANO)   # escaló, no dead-end
        WC.return_value.enviar_texto.assert_called_once()
