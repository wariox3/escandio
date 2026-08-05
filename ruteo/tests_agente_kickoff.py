"""Tests del arranque manual del agente (iniciar_sesion_conductor + endpoint).

Mockea los modelos de schema PÚBLICO (User, CtnWhatsappConexion) y WhatsappCliente;
la sesión (del tenant) se crea de verdad en la BD de test.

Correr: python manage.py test ruteo.tests_agente_kickoff
"""
from types import SimpleNamespace
from unittest.mock import patch

from django_tenants.test.cases import TenantTestCase

from ruteo.models.agente_sesion import RutAgenteSesion
from ruteo.models.despacho import RutDespacho
from ruteo.models.vehiculo import RutVehiculo
from ruteo.servicios.agente_conductor import iniciar_sesion_conductor


class _Req:
    def __init__(self, data):
        self.data = data


def _mock_user(MockUser, telefono='3001112233', nombre='Pedro', apellido='Gómez'):
    MockUser.objects.filter.return_value.first.return_value = SimpleNamespace(
        nombre=nombre, apellido=apellido, telefono=telefono,
    )


def _mock_conexion(MockConexion, empresa='Energy'):
    conexion = SimpleNamespace(contenedor=SimpleNamespace(nombre=empresa))
    MockConexion.objects.filter.return_value.select_related.return_value.first.return_value = conexion
    return conexion


class KickoffTests(TenantTestCase):

    def setUp(self):
        super().setUp()
        self.vehiculo = RutVehiculo.objects.create(placa='ABC123', estado_asignado=True)
        self.despacho = RutDespacho.objects.create(estado_aprobado=True, vehiculo=self.vehiculo, conductor_id=123)

    def test_despacho_inexistente(self):
        r = iniciar_sesion_conductor(999999)
        self.assertFalse(r['ok'])
        self.assertIn('no existe', r['mensaje'])

    def test_sin_conductor_ni_telefono(self):
        d = RutDespacho.objects.create(estado_aprobado=True, vehiculo=self.vehiculo)  # sin conductor
        r = iniciar_sesion_conductor(d.id)  # y sin telefono
        self.assertFalse(r['ok'])
        self.assertIn('número', r['mensaje'])

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    @patch('contenedor.models.CtnWhatsappConexion')
    def test_telefono_del_despachador_sin_conductor(self, MockConexion, WC):
        # Despacho por PLACA (sin conductor): el despachador indica el número.
        d = RutDespacho.objects.create(estado_aprobado=True, vehiculo=self.vehiculo)
        _mock_conexion(MockConexion)
        r = iniciar_sesion_conductor(d.id, telefono='3006134088')
        self.assertTrue(r['ok'])
        self.assertEqual(r['telefono'], '573006134088')
        ses = RutAgenteSesion.objects.filter(despacho=d, estado=RutAgenteSesion.ESTADO_ACTIVA)
        self.assertEqual(ses.count(), 1)
        self.assertEqual(ses.first().conductor_nombre, 'conductor')  # sin user -> genérico
        WC.return_value.enviar_texto.assert_called_once()

    @patch('contenedor.models.User')
    def test_conductor_sin_telefono_ni_param(self, MockUser):
        _mock_user(MockUser, telefono=None)
        r = iniciar_sesion_conductor(self.despacho.id)  # conductor sin tel, sin param
        self.assertFalse(r['ok'])
        self.assertIn('número', r['mensaje'])

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    @patch('contenedor.models.CtnWhatsappConexion')
    @patch('contenedor.models.User')
    def test_crea_sesion_y_saluda(self, MockUser, MockConexion, WC):
        _mock_user(MockUser)
        _mock_conexion(MockConexion)
        r = iniciar_sesion_conductor(self.despacho.id)

        self.assertTrue(r['ok'])
        self.assertEqual(r['telefono'], '573001112233')
        ses = RutAgenteSesion.objects.filter(despacho=self.despacho, estado=RutAgenteSesion.ESTADO_ACTIVA)
        self.assertEqual(ses.count(), 1)
        self.assertEqual(ses.first().conductor_nombre, 'Pedro Gómez')
        self.assertEqual(ses.first().historial[0]['rol'], 'agente')  # arranca con el saludo
        WC.return_value.enviar_texto.assert_called_once()
        tel, texto = WC.return_value.enviar_texto.call_args.args
        self.assertEqual(tel, '573001112233')
        self.assertIn(f'#{self.despacho.id}', texto)

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    @patch('contenedor.models.CtnWhatsappConexion')
    @patch('contenedor.models.User')
    def test_reusa_sesion_activa_no_duplica(self, MockUser, MockConexion, WC):
        _mock_user(MockUser)
        _mock_conexion(MockConexion)
        RutAgenteSesion.objects.create(
            despacho=self.despacho, telefono='573001112233',
            estado=RutAgenteSesion.ESTADO_ACTIVA, historial=[],
        )
        r = iniciar_sesion_conductor(self.despacho.id)

        self.assertTrue(r['ok'])
        self.assertIn('activa', r['mensaje'])
        self.assertEqual(RutAgenteSesion.objects.filter(despacho=self.despacho).count(), 1)  # no duplica
        WC.return_value.enviar_texto.assert_not_called()  # no re-saluda

    @patch('mensajeria.servicios.whatsapp_cliente.WhatsappCliente')
    @patch('contenedor.models.CtnWhatsappConexion')
    @patch('contenedor.models.User')
    def test_endpoint_iniciar_agente(self, MockUser, MockConexion, WC):
        from ruteo.views.despacho import RutDespachoViewSet
        _mock_user(MockUser)
        _mock_conexion(MockConexion)
        resp = RutDespachoViewSet().iniciar_agente(_Req({'id': self.despacho.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['ok'])

    def test_endpoint_sin_id(self):
        from ruteo.views.despacho import RutDespachoViewSet
        resp = RutDespachoViewSet().iniciar_agente(_Req({}))
        self.assertEqual(resp.status_code, 400)
