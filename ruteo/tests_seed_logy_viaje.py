"""Test del seed de viaje de prueba para LOGY.

Verifica que crear_viaje_prueba arma un despacho aprobado reciente con guías
pendientes y el teléfono autorizado, en el schema actual del tenant de test.

Correr: python manage.py test ruteo.tests_seed_logy_viaje
"""
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase

from ruteo.management.commands.seed_logy_viaje import crear_viaje_prueba
from ruteo.models.visita import RutVisita


class SeedViajeTests(TenantTestCase):

    def test_crea_despacho_aprobado_reciente_con_guias(self):
        d = crear_viaje_prueba(placa='logy77', telefono='573006134088', n_guias=3)
        self.assertTrue(d.estado_aprobado)
        self.assertFalse(d.estado_anulado)
        self.assertEqual(d.vehiculo.placa, 'LOGY77')            # normaliza a mayúsculas
        self.assertEqual(d.conductor_telefono, '573006134088')  # queda autorizado
        self.assertIsNotNone(d.fecha)
        pendientes = RutVisita.objects.filter(despacho=d, estado_entregado=False, estado_novedad=False)
        self.assertEqual(pendientes.count(), 3)

    def test_reusa_la_placa_si_existe(self):
        d1 = crear_viaje_prueba(placa='REUSO1', n_guias=1)
        d2 = crear_viaje_prueba(placa='REUSO1', n_guias=1)
        self.assertEqual(d1.vehiculo_id, d2.vehiculo_id)   # mismo vehículo
        self.assertNotEqual(d1.id, d2.id)                  # distinto despacho

    def test_guias_con_numeros_unicos(self):
        d = crear_viaje_prueba(placa='UNIQ1', n_guias=4)
        numeros = list(RutVisita.objects.filter(despacho=d).values_list('numero', flat=True))
        self.assertEqual(len(numeros), len(set(numeros)))  # sin duplicados
