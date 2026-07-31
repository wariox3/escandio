"""La notificacion de despacho usa 'cobro' (contra-entrega), no 'tarifa'.

La plantilla entrega_tarifa dice "el valor a pagar al recibir": ese monto es el
contra-entrega (cobro = vrCobroEntrega), no el flete (tarifa). Con guias de
Semantica tarifa=0, asi que antes esa notificacion nunca salia con el monto.

Correr: python manage.py test ruteo.tests_notificacion_cobro
"""
from decimal import Decimal

from django.test import SimpleTestCase

from ruteo.servicios.notificacion import NotificacionServicio


class PlantillaDespachoTests(SimpleTestCase):

    def _elegir(self, cobro, plantilla_config='entrega'):
        datos = {'nombre': 'Ana', 'cobro_total': Decimal(str(cobro))}
        return NotificacionServicio._plantilla_variables_despacho(
            datos, 'Energy', 'GUIA-1', plantilla_config,
        )

    def test_con_cobro_usa_entrega_tarifa_con_el_monto(self):
        plantilla, variables = self._elegir(15000)
        self.assertEqual(plantilla, 'entrega_tarifa')
        self.assertEqual(variables, ['Ana', 'Energy', 'GUIA-1', '15.000'])

    def test_sin_cobro_usa_la_plantilla_configurada(self):
        plantilla, variables = self._elegir(0)
        self.assertEqual(plantilla, 'entrega')
        self.assertEqual(variables, ['Ana', 'Energy', 'GUIA-1'])  # sin monto

    def test_plantilla_sin_variables_no_manda_parametros(self):
        plantilla, variables = self._elegir(0, plantilla_config='hello_world')
        self.assertEqual(plantilla, 'hello_world')
        self.assertEqual(variables, [])

    def test_formatea_monto_estilo_co(self):
        self.assertEqual(NotificacionServicio._formatear_monto(Decimal('1234567')), '1.234.567')
