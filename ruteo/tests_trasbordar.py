"""Regresion: POST /ruteo/despacho/trasbordar/ reventaba con ValueError -> 500.

El codigo del despacho origen se digita a mano en un input de texto libre. Llego
"17631." (con punto) y RutDespacho.objects.get(pk="17631.") lanzo ValueError, que
el except de la vista (solo DoesNotExist) no atrapaba (Sentry 415af435, tenant
energy). Ahora se coacciona a entero y se responde 400 con un mensaje claro.

De paso se cubre el bug latente: 'id' llegaba int y el origen str, asi que
'id != despacho_origen_id' era siempre verdadero y no atajaba el trasbordo de un
despacho hacia si mismo.

Correr: python manage.py test ruteo.tests_trasbordar
"""
from unittest.mock import patch

from django.test import TestCase

from ruteo.models.despacho import RutDespacho
from ruteo.views.despacho import RutDespachoViewSet


class _Peticion:
    """Solo se necesita .data: el guard responde antes de tocar BD."""

    def __init__(self, data):
        self.data = data


class TrasbordarGuardTests(TestCase):

    def _llamar(self, id, despacho_origen_id):
        return RutDespachoViewSet().trasbordar(
            _Peticion({'id': id, 'despacho_origen_id': despacho_origen_id}),
        )

    def test_origen_con_punto_no_revienta(self):
        """El caso exacto del Sentry: "17631." no debe llegar al .get(pk=...)."""
        with patch.object(RutDespacho.objects, 'get') as get:
            respuesta = self._llamar(17647, '17631.')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('numeros', respuesta.data['mensaje'])
        get.assert_not_called()

    def test_origen_no_numerico_se_rechaza(self):
        with patch.object(RutDespacho.objects, 'get') as get:
            respuesta = self._llamar(17647, 'ABC')
        self.assertEqual(respuesta.status_code, 400)
        get.assert_not_called()

    def test_mismo_despacho_int_y_str_se_ataja(self):
        """Bug latente: 17631 (int) vs "17631" (str) pasaba como diferentes."""
        with patch.object(RutDespacho.objects, 'get') as get:
            respuesta = self._llamar(17631, '17631')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('diferentes', respuesta.data['mensaje'])
        get.assert_not_called()

    def test_faltan_parametros(self):
        respuesta = self._llamar(17647, '')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('Faltan parametros', respuesta.data['mensaje'])

    def test_numerico_con_espacios_pasa_el_guard(self):
        """Se recorta y sigue: el fallo debe venir del get, no del guard."""
        with patch.object(RutDespacho.objects, 'get', side_effect=RutDespacho.DoesNotExist) as get:
            respuesta = self._llamar('  17647  ', ' 17631 ')
        get.assert_called()
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('no existe', respuesta.data['mensaje'])
