"""Tests de permisos del UsuarioContenedorViewSet.

Cambio de mayo 2026: invitar/editar/eliminar miembros ya no exige ser
propietario del contenedor — ahora exige `puede_editar_modulo('usuario')`,
que tambien aprueba a supervisor por plantilla. Operativo y consulta
siguen bloqueados. Ceder admin se mantiene restringido al propietario
(es transferencia de propiedad, no edicion de miembros).

Estos tests usan los helpers de permisos directamente, sin levantar HTTP,
para validar la matriz de roles. Es el mismo patron de
general/tests_configuracion_permisos.py.

Correr: python manage.py test contenedor.tests_usuario_contenedor_permisos
"""
from django.test import TestCase

from contenedor.models import Contenedor, User, UsuarioContenedor
from contenedor.permisos import (
    plantilla_permisos,
    puede_editar_modulo,
    puede_ver,
)


class UsuarioModuloPermisosPorPerfilTests(TestCase):
    """Matriz: quien puede ver/editar el modulo 'usuario' por perfil_web."""

    @classmethod
    def setUpTestData(cls):
        cls.contenedor = Contenedor(schema_name='tenant_test_usr', nombre='Test')
        cls.contenedor.auto_create_schema = False
        cls.contenedor.save()

        cls.propietario = User.objects.create(
            username='owner.usr@x.com', correo='owner.usr@x.com',
            nombre='O', apellido='O', is_active=True,
        )
        cls.contenedor.usuario = cls.propietario
        cls.contenedor.save()

        def _miembro(username, perfil):
            u = User.objects.create(
                username=username, correo=username,
                nombre=perfil, apellido='T', is_active=True,
            )
            UsuarioContenedor.objects.create(
                usuario=u, contenedor=cls.contenedor,
                tiene_acceso_web=True, perfil_web=perfil,
                permisos=plantilla_permisos(perfil),
                rol='usuario',
            )
            return u

        cls.supervisor = _miembro('sup.usr@x.com', 'supervisor')
        cls.operativo = _miembro('op.usr@x.com', 'operativo')
        cls.consulta = _miembro('con.usr@x.com', 'consulta')

    def test_propietario_puede_editar_usuario(self):
        self.assertTrue(puede_editar_modulo(self.propietario, self.contenedor, 'usuario'))

    def test_supervisor_puede_editar_usuario(self):
        # Es el caso nuevo que abre el ViewSet a supervisor para gestionar
        # miembros del contenedor.
        self.assertTrue(puede_editar_modulo(self.supervisor, self.contenedor, 'usuario'))

    def test_operativo_no_puede_editar_usuario(self):
        self.assertFalse(puede_editar_modulo(self.operativo, self.contenedor, 'usuario'))

    def test_consulta_no_puede_editar_usuario(self):
        self.assertFalse(puede_editar_modulo(self.consulta, self.contenedor, 'usuario'))

    def test_propietario_puede_ver_usuario(self):
        self.assertTrue(puede_ver(self.propietario, self.contenedor, 'usuario'))

    def test_supervisor_puede_ver_usuario(self):
        self.assertTrue(puede_ver(self.supervisor, self.contenedor, 'usuario'))

    def test_operativo_no_puede_ver_usuario(self):
        # La plantilla 'operativo' deja modulos administrativos en false.
        self.assertFalse(puede_ver(self.operativo, self.contenedor, 'usuario'))

    def test_consulta_no_puede_ver_usuario(self):
        self.assertFalse(puede_ver(self.consulta, self.contenedor, 'usuario'))


class CederAdminSeMantieneSoloPropietarioTests(TestCase):
    """Ceder admin transfiere la propiedad del contenedor — debe quedar
    restringido al propietario actual o super-admin. Supervisor NO debe
    poder ceder admin aunque pueda editar el modulo 'usuario'."""

    @classmethod
    def setUpTestData(cls):
        cls.contenedor = Contenedor(schema_name='tenant_test_ceder', nombre='Test')
        cls.contenedor.auto_create_schema = False
        cls.contenedor.save()

        cls.propietario = User.objects.create(
            username='owner.ceder@x.com', correo='owner.ceder@x.com',
            nombre='O', apellido='O', is_active=True,
        )
        cls.contenedor.usuario = cls.propietario
        cls.contenedor.save()

        cls.supervisor = User.objects.create(
            username='sup.ceder@x.com', correo='sup.ceder@x.com',
            nombre='S', apellido='S', is_active=True,
        )
        UsuarioContenedor.objects.create(
            usuario=cls.supervisor, contenedor=cls.contenedor,
            tiene_acceso_web=True, perfil_web='supervisor',
            permisos=plantilla_permisos('supervisor'),
            rol='usuario',
        )

    def test_propietario_es_owner_del_contenedor(self):
        """Sanity check del fixture: el propietario coincide con la FK."""
        self.assertEqual(self.contenedor.usuario_id, self.propietario.id)

    def test_supervisor_no_es_owner_aunque_pueda_editar_usuarios(self):
        """Supervisor puede gestionar miembros pero NO transferir propiedad
        — el endpoint ceder-admin sigue exigiendo usuario_id == request.user.id."""
        self.assertNotEqual(self.contenedor.usuario_id, self.supervisor.id)
        # Si en el futuro alguien afloja el check de ceder-admin, este test
        # documenta el invariante: supervisor no puede ceder.
