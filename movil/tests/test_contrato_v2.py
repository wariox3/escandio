"""Tests que blindan el contrato de la API movil v2.

El schema OpenAPI (movil/openapi_v2.yaml) es el contrato formal. El snapshot
test detecta cualquier cambio breaking. Los tests funcionales cubren el flujo
de autenticacion y el gating de permisos.

Correr: python manage.py test movil
"""
import os
import tempfile

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from contenedor.models import Contenedor, Dominio, User
from movil import responses
from movil.contrato_v2 import ENDPOINTS_MOVIL_V2

SCHEMA_PATH = os.path.join(settings.BASE_DIR, 'movil', 'openapi_v2.yaml')


def _registrar_tenant_public():
    """Mapea el host 'testserver' al schema public para que las requests lleguen."""
    public, _ = Contenedor.objects.get_or_create(
        schema_name='public', defaults={'nombre': 'public'},
    )
    Dominio.objects.get_or_create(
        domain='testserver', defaults={'tenant': public, 'is_primary': True},
    )
    return public


class ContratoV2SchemaTests(TestCase):
    """El schema OpenAPI v2 es el contrato. Si cambia, este test lo detecta."""

    def test_schema_no_cambio(self):
        with tempfile.NamedTemporaryFile('r', suffix='.yaml', delete=False) as tmp:
            tmp_path = tmp.name
        try:
            call_command('spectacular', file=tmp_path)
            with open(tmp_path) as f:
                generado = f.read()
        finally:
            os.unlink(tmp_path)
        with open(SCHEMA_PATH) as f:
            comprometido = f.read()
        self.assertEqual(
            generado, comprometido,
            'El schema OpenAPI v2 cambio respecto a movil/openapi_v2.yaml. '
            'Si el cambio es intencional, regenera el contrato con '
            '`python manage.py spectacular --file movil/openapi_v2.yaml`. '
            'Si NO era intencional, es un cambio breaking para la app movil v2.',
        )

    def test_schema_cubre_los_endpoints_del_contrato(self):
        with open(SCHEMA_PATH) as f:
            schema = f.read()
        for endpoint in ENDPOINTS_MOVIL_V2:
            ruta = endpoint.split(' ', 1)[1].replace('<id>', '{id}')
            self.assertIn(ruta, schema, f'{endpoint} falta en el schema v2')


class ContratoV2AuthTests(TestCase):
    """Flujo de autenticacion v2: tokens estandar y envelope de error unico."""

    @classmethod
    def setUpTestData(cls):
        _registrar_tenant_public()
        cls.password = 'abc12345'
        cls.user = User.objects.create(
            username='conductor@x.com', correo='conductor@x.com',
            nombre='C', apellido='C', is_active=True,
        )
        cls.user.set_password(cls.password)
        cls.user.save()

    def setUp(self):
        self.client = APIClient()

    def test_login_devuelve_tokens_estandar_y_usuario(self):
        r = self.client.post('/api/v2/auth/login/', {
            'username': self.user.username, 'password': self.password,
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn('access', r.data)
        self.assertIn('refresh', r.data)
        self.assertIn('usuario', r.data)
        self.assertEqual(r.data['usuario']['username'], self.user.username)

    def test_login_credenciales_invalidas_usa_envelope_v2(self):
        r = self.client.post('/api/v2/auth/login/', {
            'username': self.user.username, 'password': 'incorrecta',
        }, format='json')
        self.assertEqual(r.status_code, 400, r.content)
        for clave in ('codigo', 'titulo', 'mensaje'):
            self.assertIn(clave, r.data)
        self.assertEqual(r.data['codigo'], responses.COD_CREDENCIALES)

    def test_registro_crea_usuario_pendiente(self):
        r = self.client.post('/api/v2/auth/registro/', {
            'username': 'nuevo.v2@x.com', 'password': 'abc12345',
            'nombre': 'Nuevo', 'telefono': '3001234567',
            'empresa_nombre': 'Transportes XYZ',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data['estado'], 'pendiente')
        creado = User.objects.get(username='nuevo.v2@x.com')
        self.assertEqual(creado.estado_registro, 'pendiente')
        self.assertEqual(creado.empresa_nombre, 'Transportes XYZ')

    def test_login_pendiente_loguea_y_expone_estado(self):
        pend = User.objects.create(
            username='pend@x.com', correo='pend@x.com', nombre='P', apellido='P',
            is_active=True, estado_registro='pendiente',
        )
        pend.set_password('abc12345')
        pend.save()
        r = self.client.post('/api/v2/auth/login/', {
            'username': 'pend@x.com', 'password': 'abc12345',
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['usuario']['estado'], 'pendiente')

    def test_login_rechazado_bloqueado(self):
        rech = User.objects.create(
            username='rech@x.com', correo='rech@x.com', nombre='R', apellido='R',
            is_active=True, estado_registro='rechazado',
        )
        rech.set_password('abc12345')
        rech.save()
        r = self.client.post('/api/v2/auth/login/', {
            'username': 'rech@x.com', 'password': 'abc12345',
        }, format='json')
        self.assertEqual(r.status_code, 403, r.content)
        self.assertEqual(r.data['codigo'], responses.COD_SIN_PERMISO)

    def test_logout_exige_autenticacion(self):
        r = self.client.post('/api/v2/auth/logout/')
        self.assertIn(r.status_code, (401, 403), r.content)

    def test_logout_con_token_responde_200(self):
        login = self.client.post('/api/v2/auth/login/', {
            'username': self.user.username, 'password': self.password,
        }, format='json')
        r = self.client.post(
            '/api/v2/auth/logout/',
            HTTP_AUTHORIZATION=f"Bearer {login.data['access']}",
        )
        self.assertEqual(r.status_code, 200, r.content)

    def test_me_exige_autenticacion(self):
        r = self.client.get('/api/v2/auth/me/')
        self.assertIn(r.status_code, (401, 403), r.content)

    def test_me_devuelve_usuario_con_estado_y_acceso(self):
        login = self.client.post('/api/v2/auth/login/', {
            'username': self.user.username, 'password': self.password,
        }, format='json')
        r = self.client.get(
            '/api/v2/auth/me/',
            HTTP_AUTHORIZATION=f"Bearer {login.data['access']}",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['username'], self.user.username)
        self.assertIn('estado', r.data)
        self.assertIn('acceso_movil', r.data)


class ContratoV2PermisosTests(TestCase):
    """Los endpoints de tenant exigen autenticacion (EsConductorMovil)."""

    @classmethod
    def setUpTestData(cls):
        _registrar_tenant_public()

    def setUp(self):
        self.client = APIClient()

    def test_visitas_exige_autenticacion(self):
        r = self.client.get('/api/v2/visitas/')
        self.assertIn(r.status_code, (401, 403), r.content)
        self.assertIn('codigo', r.data)

    def test_novedades_tipos_exige_autenticacion(self):
        r = self.client.get('/api/v2/novedades/tipos/')
        self.assertIn(r.status_code, (401, 403), r.content)

    def test_ubicacion_exige_autenticacion(self):
        r = self.client.post('/api/v2/ubicacion/', {}, format='json')
        self.assertIn(r.status_code, (401, 403), r.content)

    def test_app_config_es_publico(self):
        r = self.client.get('/api/v2/app/config/', HTTP_X_APP_VERSION='1.0.0')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data['actualizacion_requerida'])
        for clave in ('version_minima', 'version_actual', 'actualizacion_disponible'):
            self.assertIn(clave, r.data)
