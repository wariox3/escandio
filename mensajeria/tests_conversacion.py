"""Tests del MsjConversacionViewSet — mensajes de error por estado de conexion.

Verifica que el helper _respuesta_si_no_activa devuelve codigos accionables segun
el estado del CtnWhatsappConexion. El frontend usa esos codigos para mostrar el
panel adecuado en lugar del generico "Sin conexion".

Correr: python manage.py test mensajeria.tests_conversacion
"""
from types import SimpleNamespace

from django.test import TestCase

from contenedor.models import CtnWhatsappConexion
from mensajeria.views.conversacion import MsjConversacionViewSet


class RespuestaSiNoActivaTests(TestCase):

    def setUp(self):
        self.view = MsjConversacionViewSet()

    def test_sin_registro_devuelve_no_configurado(self):
        resp = self.view._respuesta_si_no_activa(None)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['codigo'], 'whatsapp_no_configurado')

    def test_estado_pendiente_devuelve_codigo_pendiente(self):
        conex = SimpleNamespace(
            estado=CtnWhatsappConexion.ESTADO_PENDIENTE,
            error_mensaje=None,
        )
        resp = self.view._respuesta_si_no_activa(conex)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['codigo'], 'whatsapp_pendiente')

    def test_estado_error_incluye_mensaje_en_detail(self):
        conex = SimpleNamespace(
            estado=CtnWhatsappConexion.ESTADO_ERROR,
            error_mensaje='Token expirado',
        )
        resp = self.view._respuesta_si_no_activa(conex)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['codigo'], 'whatsapp_error')
        self.assertIn('Token expirado', resp.data['detail'])

    def test_estado_error_sin_mensaje_usa_fallback(self):
        conex = SimpleNamespace(
            estado=CtnWhatsappConexion.ESTADO_ERROR,
            error_mensaje=None,
        )
        resp = self.view._respuesta_si_no_activa(conex)
        self.assertEqual(resp.data['codigo'], 'whatsapp_error')
        self.assertIn('sin detalle', resp.data['detail'])

    def test_estado_activo_devuelve_none(self):
        conex = SimpleNamespace(
            estado=CtnWhatsappConexion.ESTADO_ACTIVO,
            error_mensaje=None,
        )
        self.assertIsNone(self.view._respuesta_si_no_activa(conex))
