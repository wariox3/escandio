"""Tests de permisos del ComplementoViewSet.

complemento es modulo administrativo (config de integraciones / Reddoc).
Supervisor por plantilla puede ver+editar, pero las acciones sensibles
(CRUD + validar) quedan restringidas a admin del contenedor porque tocan
credenciales y conexiones externas.

Correr: python manage.py test general.tests_complemento_permisos
"""
from django.test import TestCase

from contenedor.permisos import MODULOS_ADMINISTRATIVOS, plantilla_permisos
from general.views.complemento import ComplementoViewSet


def _clases(action):
    view = ComplementoViewSet()
    view.action = action
    return [type(p).__name__ for p in view.get_permissions()]


class ModuloRegistradoTests(TestCase):

    def test_complemento_esta_en_modulos_administrativos(self):
        self.assertIn('complemento', MODULOS_ADMINISTRATIVOS)

    def test_plantilla_supervisor_incluye_complemento_con_editar(self):
        p = plantilla_permisos('supervisor')
        self.assertEqual(p['complemento'], {'ver': True, 'editar': True})

    def test_plantilla_operativo_excluye_complemento(self):
        p = plantilla_permisos('operativo')
        self.assertEqual(p['complemento'], {'ver': False, 'editar': False})

    def test_plantilla_consulta_excluye_complemento(self):
        p = plantilla_permisos('consulta')
        self.assertEqual(p['complemento'], {'ver': False, 'editar': False})


class ComplementoViewSetTests(TestCase):

    def test_list_exige_modulo_ver(self):
        self.assertIn('PermisoModuloVer_complemento', _clases('list'))

    def test_retrieve_exige_modulo_ver(self):
        self.assertIn('PermisoModuloVer_complemento', _clases('retrieve'))

    def test_create_exige_admin_del_contenedor(self):
        # Reddoc credentials son criticas: solo propietario las toca.
        clases = _clases('create')
        self.assertIn('EsAdminDelContenedor', clases)

    def test_update_exige_admin_del_contenedor(self):
        self.assertIn('EsAdminDelContenedor', _clases('update'))

    def test_destroy_exige_admin_del_contenedor(self):
        self.assertIn('EsAdminDelContenedor', _clases('destroy'))

    def test_validar_action_exige_admin_del_contenedor(self):
        # Validar conecta a Reddoc; supervisor no deberia poder dispararlo.
        self.assertIn('EsAdminDelContenedor', _clases('validar_action'))
