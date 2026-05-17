"""Tests del flujo de aprobacion de conductores auto-registrados.

Modelo: el conductor se auto-registra desde la app v2 (queda `pendiente`); el
super-admin lo revisa y lo asigna a un contenedor (queda `aprobado`) o lo
rechaza. Ver el plan de aprobacion y movil/contrato_v2.py.

Correr: python manage.py test contenedor.tests_aprobacion
"""
from django.test import TestCase
from rest_framework.test import APIClient

from contenedor.models import Contenedor, Dominio, User, UsuarioContenedor


def _registrar_tenant_public():
    public, _ = Contenedor.objects.get_or_create(
        schema_name='public', defaults={'nombre': 'public'},
    )
    Dominio.objects.get_or_create(
        domain='testserver', defaults={'tenant': public, 'is_primary': True},
    )
    return public


class AprobacionConductoresTests(TestCase):
    """admin-lista (filtro pendientes), admin-rechazar y asignar→aprobado."""

    @classmethod
    def setUpTestData(cls):
        _registrar_tenant_public()
        cls.staff = User.objects.create(
            username='staff@x.com', correo='staff@x.com',
            nombre='S', apellido='S', is_active=True, is_staff=True,
        )
        cls.pendiente = User.objects.create(
            username='conductor.nuevo@x.com', correo='conductor.nuevo@x.com',
            nombre='Nuevo', apellido='Conductor', is_active=True,
            estado_registro='pendiente', empresa_nombre='Transportes XYZ',
        )
        # auto_create_schema=False: el test solo necesita la fila, no el schema SQL.
        cls.contenedor = Contenedor(schema_name='empresa_xyz', nombre='Transportes XYZ')
        cls.contenedor.auto_create_schema = False
        cls.contenedor.save()

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)

    def test_admin_lista_filtra_pendientes(self):
        r = self.client.get('/contenedor/usuario/admin-lista/?estado=pendientes')
        self.assertEqual(r.status_code, 200, r.content)
        ids = [u['id'] for u in r.data['results']]
        self.assertIn(self.pendiente.id, ids)
        self.assertNotIn(self.staff.id, ids)
        self.assertEqual(r.data['estadisticas']['pendientes'], 1)
        # El hint de empresa viaja al panel para que el super-admin sepa asignar.
        fila = next(u for u in r.data['results'] if u['id'] == self.pendiente.id)
        self.assertEqual(fila['empresa_nombre'], 'Transportes XYZ')
        self.assertEqual(fila['estado_registro'], 'pendiente')

    def test_admin_rechazar(self):
        r = self.client.post(
            f'/contenedor/usuario/{self.pendiente.id}/admin-rechazar/',
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.pendiente.refresh_from_db()
        self.assertEqual(self.pendiente.estado_registro, 'rechazado')

    def test_asignar_contenedor_aprueba_al_pendiente(self):
        r = self.client.post('/contenedor/usuario/admin-asignar-contenedor/', {
            'usuario_id': self.pendiente.id,
            'contenedor_id': self.contenedor.id,
            'rol': 'usuario',
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.pendiente.refresh_from_db()
        self.assertEqual(self.pendiente.estado_registro, 'aprobado')
        self.assertTrue(UsuarioContenedor.objects.filter(
            usuario_id=self.pendiente.id, contenedor_id=self.contenedor.id,
        ).exists())
