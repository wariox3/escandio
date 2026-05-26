"""Tests de permisos para los viewsets de los modulos operativos.

Blinda el cambio de mayo 2026: antes vehiculo, franja y flota tenian
`acciones_admin = ['create', 'update', 'partial_update', 'destroy']`,
lo cual hacia que el perfil 'operativo' (que por plantilla tiene
editar=True sobre esos modulos) recibiera 403 al crear/editar — bug.
Tambien blindamos novedad: ahora extiende RolMixin con modulo='novedad'
y `acciones_publicas = ['nuevo_action', 'solucionar']` para preservar
el contrato movil v1.6.4.

Estos tests inspeccionan las permission classes que arma RolMixin para
cada (viewset, action), sin levantar HTTP — mismo patron que
general/tests_configuracion_permisos.py.

Correr: python manage.py test ruteo.tests_permisos_operativos
"""
from django.test import TestCase

from ruteo.views.vehiculo import RutVehiculoViewSet
from ruteo.views.franja import RutFranjaViewSet
from ruteo.views.flota import RutFlotaViewSet
from ruteo.views.novedad import RutNovedadViewSet


def _clases(viewset_cls, action):
    view = viewset_cls()
    view.action = action
    return [type(p).__name__ for p in view.get_permissions()]


class VehiculoPermisosTests(TestCase):
    """El operativo (con vehiculo.editar=True por plantilla) debe poder
    crear/editar/eliminar vehiculos. Antes acciones_admin lo bloqueaba."""

    def test_create_no_exige_admin_del_contenedor(self):
        clases = _clases(RutVehiculoViewSet, 'create')
        self.assertNotIn('EsAdminDelContenedor', clases)
        self.assertIn('PermisoModuloEditar_vehiculo', clases)

    def test_update_no_exige_admin_del_contenedor(self):
        clases = _clases(RutVehiculoViewSet, 'update')
        self.assertNotIn('EsAdminDelContenedor', clases)
        self.assertIn('PermisoModuloEditar_vehiculo', clases)

    def test_partial_update_no_exige_admin(self):
        clases = _clases(RutVehiculoViewSet, 'partial_update')
        self.assertNotIn('EsAdminDelContenedor', clases)
        self.assertIn('PermisoModuloEditar_vehiculo', clases)

    def test_destroy_no_exige_admin(self):
        clases = _clases(RutVehiculoViewSet, 'destroy')
        self.assertNotIn('EsAdminDelContenedor', clases)
        self.assertIn('PermisoModuloEditar_vehiculo', clases)

    def test_list_exige_modulo_ver(self):
        self.assertIn(
            'PermisoModuloVer_vehiculo', _clases(RutVehiculoViewSet, 'list'),
        )


class FranjaPermisosTests(TestCase):
    def test_create_no_exige_admin_del_contenedor(self):
        clases = _clases(RutFranjaViewSet, 'create')
        self.assertNotIn('EsAdminDelContenedor', clases)
        self.assertIn('PermisoModuloEditar_franja', clases)

    def test_update_no_exige_admin(self):
        clases = _clases(RutFranjaViewSet, 'update')
        self.assertNotIn('EsAdminDelContenedor', clases)
        self.assertIn('PermisoModuloEditar_franja', clases)

    def test_destroy_no_exige_admin(self):
        clases = _clases(RutFranjaViewSet, 'destroy')
        self.assertNotIn('EsAdminDelContenedor', clases)
        self.assertIn('PermisoModuloEditar_franja', clases)


class FlotaPermisosTests(TestCase):
    def test_create_no_exige_admin_del_contenedor(self):
        clases = _clases(RutFlotaViewSet, 'create')
        self.assertNotIn('EsAdminDelContenedor', clases)
        self.assertIn('PermisoModuloEditar_flota', clases)

    def test_update_no_exige_admin(self):
        clases = _clases(RutFlotaViewSet, 'update')
        self.assertNotIn('EsAdminDelContenedor', clases)
        self.assertIn('PermisoModuloEditar_flota', clases)

    def test_destroy_no_exige_admin(self):
        clases = _clases(RutFlotaViewSet, 'destroy')
        self.assertNotIn('EsAdminDelContenedor', clases)
        self.assertIn('PermisoModuloEditar_flota', clases)

    def test_cambiar_prioridad_es_modulo_editar(self):
        """cambiar_prioridad (action custom) cae en el default del mixin:
        si hay modulo, exige PermisoModuloEditar. Antes estaba en
        acciones_admin lo cual era demasiado restrictivo."""
        clases = _clases(RutFlotaViewSet, 'cambiar_prioridad')
        self.assertNotIn('EsAdminDelContenedor', clases)
        self.assertIn('PermisoModuloEditar_flota', clases)


class NovedadPermisosTests(TestCase):
    """Novedad ahora extiende RolMixin con modulo='novedad', pero
    nuevo_action y solucionar siguen siendo publicos para no romper la
    app movil v1.6.4."""

    def test_nuevo_action_es_publico_solo_exige_authenticated(self):
        # Solo IsAuthenticated, sin PermisoModuloEditar — la app movil
        # v1.6.4 no tiene perfiles web y debe poder crear novedades.
        clases = _clases(RutNovedadViewSet, 'nuevo_action')
        self.assertEqual(clases, ['IsAuthenticated'])

    def test_solucionar_es_publico_solo_exige_authenticated(self):
        clases = _clases(RutNovedadViewSet, 'solucionar')
        self.assertEqual(clases, ['IsAuthenticated'])

    def test_create_via_drf_si_exige_permiso_de_modulo(self):
        # El CRUD estandar (no la action custom) si pasa por el modulo.
        clases = _clases(RutNovedadViewSet, 'create')
        self.assertIn('PermisoModuloEditar_novedad', clases)

    def test_list_exige_modulo_ver(self):
        self.assertIn(
            'PermisoModuloVer_novedad', _clases(RutNovedadViewSet, 'list'),
        )

    def test_destroy_no_exige_admin(self):
        clases = _clases(RutNovedadViewSet, 'destroy')
        self.assertNotIn('EsAdminDelContenedor', clases)
        self.assertIn('PermisoModuloEditar_novedad', clases)
