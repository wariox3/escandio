"""GET /ruteo/visita/{id}/ enriquecido con el contexto del despacho.

El drawer de visita y la pagina de detalle en rutenio muestran que vehiculo y
que conductor llevaron la visita entregada; el retrieve agrega vehiculo_placa y
conductor_nombre desde el despacho vinculado (y fecha_entrega via serializador).

Correr: python manage.py test ruteo.tests_visita_retrieve_contexto
"""
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from rest_framework_simplejwt.tokens import RefreshToken

from contenedor.models import User
from ruteo.models.despacho import RutDespacho
from ruteo.models.vehiculo import RutVehiculo
from ruteo.models.visita import RutVisita


class VisitaRetrieveContextoTests(TenantTestCase):

    def setUp(self):
        super().setUp()
        self.client = TenantClient(self.tenant)
        self.user = User.objects.create(
            username='operador@x.com', correo='operador@x.com',
            nombre='O', apellido='P', is_active=True,
        )
        self.token = str(RefreshToken.for_user(self.user).access_token)
        self.conductor = User.objects.create(
            username='conductor@x.com', correo='conductor@x.com',
            nombre='Juan', apellido='Perez', is_active=True,
        )
        self.vehiculo = RutVehiculo.objects.create(placa='ABC123')
        self.despacho = RutDespacho.objects.create(
            vehiculo=self.vehiculo, conductor_id=self.conductor.id,
        )
        self.visita = RutVisita.objects.create(
            ciudad_id=None, despacho=self.despacho, estado_despacho=True,
        )

    def _get(self, visita_id):
        return self.client.get(
            f'/ruteo/visita/{visita_id}/',
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )

    def test_incluye_vehiculo_y_conductor(self):
        respuesta = self._get(self.visita.id)
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(respuesta.data['vehiculo_placa'], 'ABC123')
        self.assertEqual(respuesta.data['conductor_nombre'], 'Juan Perez')
        self.assertIn('fecha_entrega', respuesta.data)

    def test_despacho_sin_vehiculo_ni_conductor(self):
        despacho = RutDespacho.objects.create()
        visita = RutVisita.objects.create(ciudad_id=None, despacho=despacho)
        respuesta = self._get(visita.id)
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertIsNone(respuesta.data['vehiculo_placa'])
        self.assertIsNone(respuesta.data['conductor_nombre'])

    def test_visita_sin_despacho_no_revienta(self):
        visita = RutVisita.objects.create(ciudad_id=None)
        respuesta = self._get(visita.id)
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertNotIn('vehiculo_placa', respuesta.data)
