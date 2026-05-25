"""Tests de permisos del ConfiguracionViewSet.

Blinda dos cosas:

1) La accion 'update' / 'partial_update' / 'create' / 'destroy' NO debe
   exigir EsAdminDelContenedor. Antes existia
   `acciones_admin = ['create', 'update', 'partial_update', 'destroy']`
   en el viewset, lo que rebotaba con 403 a supervisor pese a tener
   configuracion.editar = True por plantilla. Si alguien re-introduce
   acciones_admin con esas actions, estos tests caen.

2) `puede_editar_modulo('configuracion')` y `puede_ver('configuracion')`
   por perfil_web del UsuarioContenedor: propietario y supervisor
   pueden editar; operativo y consulta no.

Correr: python manage.py test general.tests_configuracion_permisos
"""
from django.test import TestCase

from contenedor.models import Contenedor, User, UsuarioContenedor
from contenedor.permisos import (
    plantilla_permisos,
    puede_editar_modulo,
    puede_ver,
)
from general.views.configuracion import ConfiguracionViewSet


class ConfiguracionViewSetGatingTests(TestCase):
    """No depende de DB: inspecciona las permission classes que arma el
    RolMixin para cada action."""

    def _clases(self, action):
        view = ConfiguracionViewSet()
        view.action = action
        return [type(p).__name__ for p in view.get_permissions()]

    def test_update_no_exige_admin_del_contenedor(self):
        clases = self._clases('update')
        self.assertNotIn('EsAdminDelContenedor', clases)
        self.assertIn('PermisoModuloEditar_configuracion', clases)

    def test_partial_update_no_exige_admin_del_contenedor(self):
        clases = self._clases('partial_update')
        self.assertNotIn('EsAdminDelContenedor', clases)
        self.assertIn('PermisoModuloEditar_configuracion', clases)

    def test_create_no_exige_admin_del_contenedor(self):
        clases = self._clases('create')
        self.assertNotIn('EsAdminDelContenedor', clases)
        self.assertIn('PermisoModuloEditar_configuracion', clases)

    def test_destroy_no_exige_admin_del_contenedor(self):
        clases = self._clases('destroy')
        self.assertNotIn('EsAdminDelContenedor', clases)
        self.assertIn('PermisoModuloEditar_configuracion', clases)

    def test_retrieve_exige_modulo_ver(self):
        self.assertIn('PermisoModuloVer_configuracion', self._clases('retrieve'))

    def test_list_exige_modulo_ver(self):
        self.assertIn('PermisoModuloVer_configuracion', self._clases('list'))


class ConfiguracionPorPerfilWebTests(TestCase):
    """puede_editar_modulo / puede_ver para 'configuracion' segun perfil_web."""

    @classmethod
    def setUpTestData(cls):
        # auto_create_schema=False: el test solo necesita la fila, no el schema SQL.
        cls.contenedor = Contenedor(schema_name='tenant_test_cfg', nombre='Test')
        cls.contenedor.auto_create_schema = False
        cls.contenedor.save()

        cls.propietario = User.objects.create(
            username='owner@x.com', correo='owner@x.com',
            nombre='O', apellido='O', is_active=True,
        )
        cls.contenedor.usuario = cls.propietario
        cls.contenedor.save()

        def _miembro(username, perfil):
            u = User.objects.create(
                username=username, correo=username,
                nombre=perfil, apellido='Test', is_active=True,
            )
            UsuarioContenedor.objects.create(
                usuario=u, contenedor=cls.contenedor,
                tiene_acceso_web=True, perfil_web=perfil,
                permisos=plantilla_permisos(perfil),
                rol='usuario',
            )
            return u

        cls.supervisor = _miembro('sup@x.com', 'supervisor')
        cls.operativo = _miembro('op@x.com', 'operativo')
        cls.consulta = _miembro('con@x.com', 'consulta')

    def test_propietario_puede_editar(self):
        self.assertTrue(puede_editar_modulo(self.propietario, self.contenedor, 'configuracion'))

    def test_supervisor_puede_editar(self):
        # Este es EL caso que provocaba el reporte de produccion: supervisor
        # con configuracion.editar=True en la plantilla pero rebotado por
        # acciones_admin del viewset.
        self.assertTrue(puede_editar_modulo(self.supervisor, self.contenedor, 'configuracion'))

    def test_operativo_no_puede_editar(self):
        self.assertFalse(puede_editar_modulo(self.operativo, self.contenedor, 'configuracion'))

    def test_consulta_no_puede_editar(self):
        self.assertFalse(puede_editar_modulo(self.consulta, self.contenedor, 'configuracion'))

    def test_propietario_puede_ver(self):
        self.assertTrue(puede_ver(self.propietario, self.contenedor, 'configuracion'))

    def test_supervisor_puede_ver(self):
        self.assertTrue(puede_ver(self.supervisor, self.contenedor, 'configuracion'))

    def test_operativo_no_puede_ver(self):
        # La plantilla 'operativo' deja configuracion.ver = False.
        self.assertFalse(puede_ver(self.operativo, self.contenedor, 'configuracion'))

    def test_consulta_no_puede_ver(self):
        self.assertFalse(puede_ver(self.consulta, self.contenedor, 'configuracion'))
