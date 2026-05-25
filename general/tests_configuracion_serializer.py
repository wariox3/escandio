"""Tests del GenConfiguracionSerializador, en particular la coercion de
strings vacios a None para los campos nullable.

Motivo: el frontend de configuracion (rutenio) inicializa el form con
rut_latitud='' y rut_longitud='', y al limpiar el ng-select del buscador
de direcciones tambien pone ''. DecimalField rechaza "" como invalido y
devuelve 400, lo que en algunos deployments cae a status:0 en Angular y
muestra un toast confuso "Sin conexion".

El serializer ahora coerce esos "" a None antes de validar — este test
blinda esa coercion.

Usamos `partial=True` para evitar el lookup del PK (`id`) sobre la tabla
`gen_configuracion`, que es tenant-scoped y no existe en el schema
`public` durante los tests. Solo nos interesa probar la coercion, no la
persistencia.

Correr: python manage.py test general.tests_configuracion_serializer
"""
from django.test import TestCase

from general.serializers.configuracion import GenConfiguracionSerializador


class GenConfiguracionSerializadorCoercionTests(TestCase):
    """Caso de regresion: el serializer debe aceptar "" en lat/lon y
    direccion_origen, coercerlos a None."""

    def test_acepta_strings_vacios_en_lat_lon_y_los_pasa_a_none(self):
        serializador = GenConfiguracionSerializador(
            data={
                'rut_latitud': '',
                'rut_longitud': '',
                'rut_direccion_origen': '',
            },
            partial=True,
        )
        self.assertTrue(serializador.is_valid(), serializador.errors)
        self.assertIsNone(serializador.validated_data.get('rut_latitud'))
        self.assertIsNone(serializador.validated_data.get('rut_longitud'))
        self.assertIsNone(serializador.validated_data.get('rut_direccion_origen'))

    def test_acepta_string_vacio_en_plantilla_whatsapp(self):
        serializador = GenConfiguracionSerializador(
            data={'rut_whatsapp_plantilla_despacho': ''},
            partial=True,
        )
        self.assertTrue(serializador.is_valid(), serializador.errors)
        self.assertIsNone(
            serializador.validated_data.get('rut_whatsapp_plantilla_despacho'),
        )

    def test_acepta_valores_validos_sin_modificarlos(self):
        # Sanity: la coercion no debe afectar valores legitimos.
        serializador = GenConfiguracionSerializador(
            data={
                'rut_latitud': '6.234567890123456',
                'rut_longitud': '-75.567890123456789',
                'rut_direccion_origen': 'Cl 9 Sur, Medellin',
            },
            partial=True,
        )
        self.assertTrue(serializador.is_valid(), serializador.errors)
        self.assertEqual(
            str(serializador.validated_data['rut_latitud']),
            '6.234567890123456',
        )
        self.assertEqual(
            serializador.validated_data['rut_direccion_origen'],
            'Cl 9 Sur, Medellin',
        )

    def test_null_explicito_tambien_se_acepta(self):
        serializador = GenConfiguracionSerializador(
            data={
                'rut_latitud': None,
                'rut_longitud': None,
                'rut_direccion_origen': None,
            },
            partial=True,
        )
        self.assertTrue(serializador.is_valid(), serializador.errors)
