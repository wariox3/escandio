"""Tests que blindan el contrato movil v1.6.4. NO se deben relajar.

Si uno falla, la app movil publicada en stores se rompe. Antes de modificar
una de las views referenciadas en contenedor/contrato_movil.py, asegurate de
que estos tests siguen pasando.

Correr: python manage.py test contenedor.tests_contrato_movil
"""
import inspect

from django.test import TestCase
from rest_framework.test import APIClient

from contenedor.models import User, Contenedor, Dominio


class ContratoMovilV164Tests(TestCase):
    """Replica los payloads exactos que la app v1.6.4 envia."""

    @classmethod
    def setUpTestData(cls):
        # django-tenants enruta por host; mapeamos 'testserver' al schema public
        # para que las requests de los tests lleguen a las views.
        public_tenant, _ = Contenedor.objects.get_or_create(
            schema_name='public',
            defaults={'nombre': 'public'},
        )
        Dominio.objects.get_or_create(
            domain='testserver',
            defaults={'tenant': public_tenant, 'is_primary': True},
        )
        cls.password = 'abc12345'
        cls.user = User.objects.create(
            username='movil@x.com',
            correo='movil@x.com',
            nombre='M',
            apellido='M',
            is_active=True,
        )
        cls.user.set_password(cls.password)
        cls.user.save()

    def setUp(self):
        self.client = APIClient()

    def test_login_acepta_proyecto_RUTEOAPP_y_devuelve_token_y_refresh_token(self):
        r = self.client.post('/seguridad/login/', {
            'username': self.user.username,
            'password': self.password,
            'proyecto': 'RUTEOAPP',
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn('token', r.data)
        # critico: la clave es con guion, no underscore
        self.assertIn('refresh-token', r.data)
        self.assertIn('user', r.data)

    def test_proyectos_validos_incluye_RUTEOAPP(self):
        # blindaje: si alguien quita RUTEOAPP del whitelist, la app no logra loguear
        from contenedor.views import seguridad
        src = inspect.getsource(seguridad.Login.post)
        self.assertIn("'RUTEOAPP'", src)

    def test_registro_con_payload_exacto_de_app_v164(self):
        r = self.client.post('/contenedor/usuario/nuevo/', {
            'username': 'nuevo.movil@x.com',
            'password': 'abc12345',
            'confirmarPassword': 'abc12345',
            'aceptarTerminosCondiciones': True,
            'aplicacion': 'ruteo',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIn('usuario', r.data)
        self.assertTrue(User.objects.filter(username='nuevo.movil@x.com').exists())

    def test_registro_persiste_aplicacion(self):
        self.client.post('/contenedor/usuario/nuevo/', {
            'username': 'aplicacion.movil@x.com',
            'password': 'abc12345',
            'aplicacion': 'ruteo',
        }, format='json')
        u = User.objects.get(username='aplicacion.movil@x.com')
        self.assertEqual(u.aplicacion, 'ruteo')

    def test_registro_acepta_payload_sin_aplicacion(self):
        # algun cliente legacy podria no enviar aplicacion - no debe romper
        r = self.client.post('/contenedor/usuario/nuevo/', {
            'username': 'sin.aplicacion@x.com',
            'password': 'abc12345',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)

    def test_RutVisitaViewSet_lista_es_publica_para_movil(self):
        from ruteo.views.visita import RutVisitaViewSet
        publicas = getattr(RutVisitaViewSet, 'acciones_publicas', [])
        self.assertIn('list', publicas)
        self.assertIn('retrieve', publicas)
        # Es el nombre del metodo (entrega_action), no el url_path (entrega).
        # RolMixin matchea contra self.action que DRF setea al nombre del metodo.
        self.assertIn('entrega_action', publicas)

    def test_RutVisitaViewSet_entrega_es_alcanzable_con_solo_jwt(self):
        # Blindaje runtime: pega contra el endpoint real con un JWT minimo
        # (sin UsuarioContenedor, sin perfil movil). El contrato exige que
        # baste IsAuthenticated; cualquier status != 403 es aceptable.
        # Si esto rompe (status 403), la app v1.6.4 publicada se rompe.
        login = self.client.post('/seguridad/login/', {
            'username': self.user.username,
            'password': self.password,
            'proyecto': 'RUTEOAPP',
        }, format='json')
        self.assertEqual(login.status_code, 200, login.content)
        token = login.data['token']
        r = self.client.post(
            '/ruteo/visita/entrega/',
            {},
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertNotEqual(
            r.status_code, 403,
            f'entrega devolvio 403 ({r.content!r}); rompe contrato v1.6.4',
        )

    def test_RutUbicacionViewSet_create_es_alcanzable_con_solo_jwt(self):
        # La app envia tracking de ubicacion en background. El contrato exige
        # que POST /ruteo/ubicacion/ siga siendo alcanzable con solo un JWT:
        # cualquier 403 (permiso) o 404/405 (ruta/metodo eliminados) rompe
        # el tracking de la app v1.6.4 publicada.
        login = self.client.post('/seguridad/login/', {
            'username': self.user.username,
            'password': self.password,
            'proyecto': 'RUTEOAPP',
        }, format='json')
        self.assertEqual(login.status_code, 200, login.content)
        token = login.data['token']
        r = self.client.post(
            '/ruteo/ubicacion/',
            {},
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertNotIn(
            r.status_code, (403, 404, 405),
            f'ubicacion devolvio {r.status_code} ({r.content!r}); rompe contrato v1.6.4',
        )

    def test_default_tiene_acceso_movil_es_True(self):
        # blindaje: el default no debe revertirse a False, eso bloquearia
        # a conductores invitados existentes en cualquier viewset con RolMixin
        from contenedor.models import UsuarioContenedor
        field = UsuarioContenedor._meta.get_field('tiene_acceso_movil')
        self.assertTrue(field.default, 'tiene_acceso_movil debe seguir siendo default=True')
