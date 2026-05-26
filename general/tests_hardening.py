"""Tests del hardening de permisos en viewsets que antes usaban
[IsAuthenticated] sin gating por rol o modulo.

Cambios cubiertos (mayo 2026):
- api_key: ahora solo admin del contenedor (no cualquier miembro).
- archivo: ahora pasa por RolMixin (al menos limita a miembros editores).
- ubicacion: RolMixin + modulo='despacho', con autocompletar/place_details
  publicos (los usa el buscador del frontend en /configuracion).
- seguimiento: RolMixin + modulo='despacho'.
- alerta: RolMixin + modulo='despacho'.

Correr: python manage.py test general.tests_hardening
"""
from django.test import TestCase

from general.views.api_key import ApiKeyViewSet
from general.views.archivo import ArchivoViewSet
from ruteo.views.alerta import RutAlertaViewSet
from ruteo.views.seguimiento import RutSeguimientoViewSet
from ruteo.views.ubicacion import RutUbicacionViewSet


def _clases(viewset_cls, action):
    view = viewset_cls()
    view.action = action
    return [type(p).__name__ for p in view.get_permissions()]


class ApiKeyTests(TestCase):

    def test_create_exige_admin_del_contenedor(self):
        clases = _clases(ApiKeyViewSet, 'create')
        self.assertIn('EsAdminDelContenedor', clases)

    def test_destroy_exige_admin_del_contenedor(self):
        clases = _clases(ApiKeyViewSet, 'destroy')
        self.assertIn('EsAdminDelContenedor', clases)

    def test_list_exige_admin_del_contenedor(self):
        clases = _clases(ApiKeyViewSet, 'list')
        self.assertIn('EsAdminDelContenedor', clases)


class UbicacionTests(TestCase):

    def test_autocompletar_es_publico(self):
        # Lo consume el buscador del frontend en /configuracion sin perfil
        # operativo necesariamente. Debe quedar como acciones_publicas.
        self.assertEqual(_clases(RutUbicacionViewSet, 'autocompletar'),
                         ['IsAuthenticated'])

    def test_place_details_es_publico(self):
        self.assertEqual(_clases(RutUbicacionViewSet, 'place_details'),
                         ['IsAuthenticated'])

    def test_create_es_publico_para_app_movil(self):
        # RETROCOMPAT v1.6.4: la app movil envia tracking via POST /ruteo/ubicacion/
        self.assertEqual(_clases(RutUbicacionViewSet, 'create'),
                         ['IsAuthenticated'])

    def test_destroy_pasa_por_modulo_despacho(self):
        clases = _clases(RutUbicacionViewSet, 'destroy')
        self.assertIn('PermisoModuloEditar_despacho', clases)


class SeguimientoTests(TestCase):

    def test_create_pasa_por_modulo_despacho(self):
        self.assertIn('PermisoModuloEditar_despacho',
                      _clases(RutSeguimientoViewSet, 'create'))

    def test_list_exige_modulo_ver(self):
        self.assertIn('PermisoModuloVer_despacho',
                      _clases(RutSeguimientoViewSet, 'list'))


class AlertaTests(TestCase):

    def test_destroy_pasa_por_modulo_despacho(self):
        self.assertIn('PermisoModuloEditar_despacho',
                      _clases(RutAlertaViewSet, 'destroy'))

    def test_list_exige_modulo_ver(self):
        self.assertIn('PermisoModuloVer_despacho',
                      _clases(RutAlertaViewSet, 'list'))


class ArchivoTests(TestCase):

    def test_create_exige_miembro_editor(self):
        # Sin modulo declarado, el RolMixin cae en EsMiembroEditor para
        # escritura (admin/operativo/supervisor; bloquea consulta).
        self.assertIn('EsMiembroEditor', _clases(ArchivoViewSet, 'create'))

    def test_list_exige_miembro(self):
        self.assertIn('EsMiembroDelContenedor', _clases(ArchivoViewSet, 'list'))
