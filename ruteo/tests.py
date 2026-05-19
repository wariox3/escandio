from django.test import TestCase

from contenedor.models import User
from ruteo.models.despacho import RutDespacho
from ruteo.serializers.despacho import RutDespachoSerializador


class DespachoConductorTests(TestCase):
    """El despacho expone el conductor asignado (id plano a contenedor.User)."""

    def test_serializer_resuelve_nombre_del_conductor(self):
        conductor = User.objects.create(
            username='cond.desp@x.com', correo='cond.desp@x.com',
            nombre='Pedro', apellido='Ruiz', is_active=True,
        )
        data = RutDespachoSerializador(RutDespacho(conductor_id=conductor.id)).data
        self.assertEqual(data['conductor_id'], conductor.id)
        self.assertEqual(data['conductor_nombre'], 'Pedro Ruiz')

    def test_serializer_sin_conductor_devuelve_none(self):
        data = RutDespachoSerializador(RutDespacho()).data
        self.assertIsNone(data['conductor_id'])
        self.assertIsNone(data['conductor_nombre'])
