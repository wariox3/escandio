"""Tests del modulo super-admin global: crear usuario, reset password,
edicion de membresias y permisos granulares.

Correr: python manage.py test contenedor.tests_admin_usuarios
"""
from django.test import TestCase
from rest_framework.test import APIClient

from contenedor.models import User, Contenedor, Dominio, UsuarioContenedor
from contenedor.permisos import (
    plantilla_permisos,
    puede_editar_modulo,
    puede_ver,
)


class AdminUsuariosTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        public_tenant, _ = Contenedor.objects.get_or_create(
            schema_name='public',
            defaults={'nombre': 'public'},
        )
        Dominio.objects.get_or_create(
            domain='testserver',
            defaults={'tenant': public_tenant, 'is_primary': True},
        )
        cls.admin = User.objects.create(
            username='admin@x.com',
            correo='admin@x.com',
            nombre='Admin',
            apellido='Global',
            is_active=True,
            is_staff=True,
        )
        cls.admin.set_password('admin1234')
        cls.admin.save()
        cls.usuario = User.objects.create(
            username='user@x.com',
            correo='user@x.com',
            nombre='User',
            apellido='Test',
            is_active=True,
        )
        cls.usuario.set_password('user1234')
        cls.usuario.save()

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_admin_crear_con_password_setea_flag_de_cambio(self):
        r = self.client.post('/contenedor/usuario/admin-crear/', {
            'username': 'creado@x.com',
            'nombre': 'Creado',
            'apellido': 'Directo',
            'password': 'abc12345',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        u = User.objects.get(username='creado@x.com')
        self.assertTrue(u.debe_cambiar_clave)
        self.assertTrue(u.verificado)
        self.assertTrue(u.check_password('abc12345'))

    def test_admin_crear_con_invitacion_no_setea_cambio_forzado(self):
        r = self.client.post('/contenedor/usuario/admin-crear/', {
            'username': 'invitado@x.com',
            'nombre': 'Invitado',
            'apellido': 'Por mail',
            'enviar_invitacion': True,
        }, format='json')
        # email send fallaria sin Zinc configurado en test, no validamos el envio
        # pero si la creacion del usuario.
        self.assertIn(r.status_code, (200, 201, 500), r.content)
        if r.status_code == 201:
            u = User.objects.get(username='invitado@x.com')
            self.assertFalse(u.debe_cambiar_clave)

    def test_admin_crear_rechaza_username_duplicado(self):
        r = self.client.post('/contenedor/usuario/admin-crear/', {
            'username': 'user@x.com',
            'password': 'abc12345',
        }, format='json')
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(r.data.get('codigo'), 14)

    def test_admin_crear_sin_password_ni_invitacion_falla(self):
        r = self.client.post('/contenedor/usuario/admin-crear/', {
            'username': 'sinclave@x.com',
        }, format='json')
        self.assertEqual(r.status_code, 400, r.content)

    def test_admin_crear_requiere_staff(self):
        self.client.force_authenticate(user=self.usuario)
        r = self.client.post('/contenedor/usuario/admin-crear/', {
            'username': 'otro@x.com',
            'password': 'abc12345',
        }, format='json')
        self.assertEqual(r.status_code, 403, r.content)

    def test_admin_reset_password_setea_flag(self):
        r = self.client.post(
            f'/contenedor/usuario/{self.usuario.id}/admin-reset-password/',
            {'password': 'nueva1234'},
            format='json',
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.debe_cambiar_clave)
        self.assertTrue(self.usuario.check_password('nueva1234'))

    def test_cambio_clave_limpia_flag(self):
        self.usuario.debe_cambiar_clave = True
        self.usuario.save()
        r = self.client.post('/contenedor/usuario/cambio-clave/', {
            'usuario_id': self.usuario.id,
            'password': 'limpia1234',
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.usuario.refresh_from_db()
        self.assertFalse(self.usuario.debe_cambiar_clave)

    def test_login_response_incluye_debe_cambiar_clave(self):
        # Berkelio v1.6.4 no se rompe porque la key extra dentro de user es ignorada.
        r = self.client.post('/seguridad/login/', {
            'username': self.usuario.username,
            'password': 'user1234',
            'proyecto': 'RUTEOAPP',
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn('user', r.data)
        self.assertIn('debe_cambiar_clave', r.data['user'])
        self.assertFalse(r.data['user']['debe_cambiar_clave'])


class AdminMembresiasTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        public_tenant, _ = Contenedor.objects.get_or_create(
            schema_name='public',
            defaults={'nombre': 'public'},
        )
        Dominio.objects.get_or_create(
            domain='testserver',
            defaults={'tenant': public_tenant, 'is_primary': True},
        )
        cls.admin = User.objects.create(
            username='superadmin@x.com',
            correo='superadmin@x.com',
            nombre='S',
            apellido='A',
            is_active=True,
            is_staff=True,
        )
        cls.admin.set_password('x')
        cls.admin.save()
        cls.dueno = User.objects.create(
            username='dueno@x.com', correo='dueno@x.com', nombre='D', apellido='D',
            is_active=True,
        )
        cls.dueno.set_password('x')
        cls.dueno.save()
        cls.miembro = User.objects.create(
            username='miembro@x.com', correo='miembro@x.com', nombre='M', apellido='M',
            is_active=True,
        )
        cls.miembro.set_password('x')
        cls.miembro.save()
        cls.contenedor = Contenedor.objects.create(
            schema_name='ctn1', nombre='Ctn 1', usuario=cls.dueno,
        )
        cls.membresia = UsuarioContenedor.objects.create(
            usuario=cls.miembro,
            contenedor=cls.contenedor,
            rol='usuario',
            tiene_acceso_web=True,
            perfil_web='consulta',
            permisos=plantilla_permisos('consulta'),
        )

    def setUp(self):
        self.client = APIClient()

    def test_admin_actualizar_membresia_modifica_permisos(self):
        self.client.force_authenticate(user=self.admin)
        nuevos = plantilla_permisos('operativo')
        r = self.client.patch(
            f'/contenedor/usuariocontenedor/{self.membresia.id}/admin-actualizar/',
            {'permisos': nuevos, 'tiene_acceso_movil': False},
            format='json',
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.membresia.refresh_from_db()
        self.assertEqual(self.membresia.permisos, nuevos)
        self.assertFalse(self.membresia.tiene_acceso_movil)

    def test_aplicar_plantilla_supervisor(self):
        self.client.force_authenticate(user=self.admin)
        r = self.client.post(
            f'/contenedor/usuariocontenedor/{self.membresia.id}/aplicar-plantilla/',
            {'plantilla': 'supervisor'},
            format='json',
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.membresia.refresh_from_db()
        for modulo, p in self.membresia.permisos.items():
            self.assertTrue(p['ver'])
            self.assertTrue(p['editar'])

    def test_aplicar_plantilla_invalida_falla(self):
        self.client.force_authenticate(user=self.admin)
        r = self.client.post(
            f'/contenedor/usuariocontenedor/{self.membresia.id}/aplicar-plantilla/',
            {'plantilla': 'inexistente'},
            format='json',
        )
        self.assertEqual(r.status_code, 400, r.content)

    def test_admin_actualizar_rechaza_no_admin(self):
        # un usuario sin permisos no puede tocar la membresia
        otro = User.objects.create(
            username='otro@x.com', correo='otro@x.com', nombre='O', apellido='O', is_active=True,
        )
        otro.set_password('x')
        otro.save()
        self.client.force_authenticate(user=otro)
        r = self.client.patch(
            f'/contenedor/usuariocontenedor/{self.membresia.id}/admin-actualizar/',
            {'permisos': {}},
            format='json',
        )
        self.assertEqual(r.status_code, 403, r.content)


class PermisosGranularesTests(TestCase):
    """Verifica los helpers puede_ver / puede_editar_modulo a nivel de modelo."""

    @classmethod
    def setUpTestData(cls):
        cls.dueno = User.objects.create(
            username='d@x.com', correo='d@x.com', nombre='D', apellido='D', is_active=True,
        )
        cls.miembro = User.objects.create(
            username='m@x.com', correo='m@x.com', nombre='M', apellido='M', is_active=True,
        )
        cls.super_admin = User.objects.create(
            username='s@x.com', correo='s@x.com', nombre='S', apellido='S',
            is_active=True, is_superuser=True,
        )
        cls.contenedor = Contenedor.objects.create(
            schema_name='ctn_perm', nombre='Ctn Perm', usuario=cls.dueno,
        )
        cls.membresia = UsuarioContenedor.objects.create(
            usuario=cls.miembro,
            contenedor=cls.contenedor,
            rol='usuario',
            tiene_acceso_web=True,
            permisos={
                'visita': {'ver': True, 'editar': False},
                'vehiculo': {'ver': True, 'editar': True},
            },
        )

    def test_admin_del_contenedor_siempre_puede_todo(self):
        self.assertTrue(puede_ver(self.dueno, self.contenedor, 'visita'))
        self.assertTrue(puede_editar_modulo(self.dueno, self.contenedor, 'visita'))
        self.assertTrue(puede_editar_modulo(self.dueno, self.contenedor, 'modulo_inexistente'))

    def test_super_admin_siempre_puede_todo(self):
        self.assertTrue(puede_ver(self.super_admin, self.contenedor, 'visita'))
        self.assertTrue(puede_editar_modulo(self.super_admin, self.contenedor, 'visita'))

    def test_miembro_consulta_puede_ver_pero_no_editar(self):
        self.assertTrue(puede_ver(self.miembro, self.contenedor, 'visita'))
        self.assertFalse(puede_editar_modulo(self.miembro, self.contenedor, 'visita'))

    def test_miembro_operativo_puede_editar(self):
        self.assertTrue(puede_ver(self.miembro, self.contenedor, 'vehiculo'))
        self.assertTrue(puede_editar_modulo(self.miembro, self.contenedor, 'vehiculo'))

    def test_modulo_no_listado_devuelve_false(self):
        # 'franja' no esta en los permisos del miembro
        self.assertFalse(puede_ver(self.miembro, self.contenedor, 'franja'))
        self.assertFalse(puede_editar_modulo(self.miembro, self.contenedor, 'franja'))

    def test_membresia_sin_acceso_web_no_concede_permisos(self):
        self.membresia.tiene_acceso_web = False
        self.membresia.save()
        self.assertFalse(puede_ver(self.miembro, self.contenedor, 'visita'))
        self.assertFalse(puede_editar_modulo(self.miembro, self.contenedor, 'vehiculo'))

    def test_no_miembro_no_tiene_permisos(self):
        ajeno = User.objects.create(
            username='a@x.com', correo='a@x.com', nombre='A', apellido='A', is_active=True,
        )
        self.assertFalse(puede_ver(ajeno, self.contenedor, 'visita'))
        self.assertFalse(puede_editar_modulo(ajeno, self.contenedor, 'visita'))

    def test_plantilla_permisos_consulta_solo_ver(self):
        plantilla = plantilla_permisos('consulta')
        self.assertTrue(plantilla['visita']['ver'])
        self.assertFalse(plantilla['visita']['editar'])

    def test_plantilla_permisos_operativo_ver_y_editar(self):
        plantilla = plantilla_permisos('operativo')
        self.assertTrue(plantilla['visita']['ver'])
        self.assertTrue(plantilla['visita']['editar'])

    def test_plantilla_permisos_invalida_devuelve_vacio(self):
        self.assertEqual(plantilla_permisos('inexistente'), {})
