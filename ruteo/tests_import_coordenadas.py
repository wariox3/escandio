"""Regresion: import (excel/complemento) no debe fallar por coordenadas con
mas de 15 decimales.

La geocodificacion entrega floats que, al pasar a Decimal, traen >15 decimales
(-75.12345678901234567). DecimalField(decimal_places=15) los rechazaba
("Asegurese de que no haya mas de 15 decimales") y rompia la fila. Ahora
RutVisitaSerializador redondea lat/long a 15 decimales antes de validar.

Correr: python manage.py test ruteo.tests_import_coordenadas
"""
from decimal import Decimal

from django.test import SimpleTestCase

from ruteo.serializers.visita import _redondear_coordenada, RutVisitaSerializador


class RedondearCoordenadaTests(SimpleTestCase):
    def test_recorta_a_15_decimales(self):
        r = _redondear_coordenada('-75.1234567890123456789')  # 19 decimales
        self.assertEqual(r.as_tuple().exponent, -15)

    def test_none_y_vacio_pasan_igual(self):
        self.assertIsNone(_redondear_coordenada(None))
        self.assertEqual(_redondear_coordenada(''), '')

    def test_valor_normal_se_conserva_numericamente(self):
        self.assertEqual(_redondear_coordenada('4.710376'), Decimal('4.710376'))

    def test_no_numerico_se_deja_para_el_validador(self):
        self.assertEqual(_redondear_coordenada('abc'), 'abc')


class SerializadorCoordenadaTests(SimpleTestCase):
    def test_longitud_con_muchos_decimales_ya_no_falla(self):
        # Reproduce la Fila 380: longitud con >15 decimales.
        s = RutVisitaSerializador(data={
            'latitud': '4.1234567890123456789',
            'longitud': '-75.1234567890123456789',
        })
        s.is_valid()
        # El bug era un error especifico en estos campos; ya no debe aparecer
        # (otros campos requeridos pueden seguir en errors, no importa aqui).
        self.assertNotIn('latitud', s.errors)
        self.assertNotIn('longitud', s.errors)
