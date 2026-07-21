"""Regresion: el complemento (Semantica) responde 200 con un cuerpo de error.

El complemento NO usa codigos HTTP para los errores de negocio: ante un despacho
inexistente responde 200 con {'error': true, 'errorMensaje': ...}. El codigo
leia datos['despacho'] de una -> KeyError -> 500 opaco en
POST /ruteo/despacho/nuevo-complemento/ (Sentry b4ac27f2, tenant energy).

Ahora se devuelve {'error': True, 'mensaje': <motivo del complemento>} y la
vista responde 400 con ese motivo.

Correr: python manage.py test ruteo.tests_complemento_respuesta
"""
from unittest.mock import patch

from django.test import TestCase

from ruteo.views.despacho import RutDespachoViewSet
from utilidades.holmio import Holmio


def _respuesta_ok(datos):
    return {'status': 200, 'datos': datos}


class DespachoDetalleTests(TestCase):

    def _llamar(self, datos):
        with patch.object(Holmio, 'consumirPost', return_value=_respuesta_ok(datos)):
            return Holmio().despacho_detalle({'codigo_despacho': '123'})

    def test_sin_clave_despacho_no_revienta(self):
        """El caso exacto del Sentry: 200 sin la clave 'despacho'."""
        resultado = self._llamar({'error': True, 'errorMensaje': 'El despacho no existe'})
        self.assertTrue(resultado['error'])
        self.assertIn('El despacho no existe', resultado['mensaje'])

    def test_sin_motivo_usa_mensaje_generico(self):
        resultado = self._llamar({})
        self.assertTrue(resultado['error'])
        self.assertIn('no devolvio los datos esperados', resultado['mensaje'])

    def test_despacho_vacio_se_rechaza(self):
        """Un dict vacio pasaria el 'error == False' y reventaria al leer las claves."""
        self.assertTrue(self._llamar({'despacho': {}})['error'])

    def test_datos_no_dict_no_revienta(self):
        self.assertTrue(self._llamar([])['error'])

    def test_despacho_valido_pasa(self):
        resultado = self._llamar({'despacho': {'vehiculoPlaca': 'ABC123', 'codigoDespachoPk': 55}})
        self.assertFalse(resultado['error'])
        self.assertEqual(resultado['despacho']['vehiculoPlaca'], 'ABC123')


class RuteoPendienteTests(TestCase):

    def _llamar(self, datos):
        with patch.object(Holmio, 'consumirPost', return_value=_respuesta_ok(datos)):
            return Holmio().ruteo_pendiente({'limite': 10})

    def test_sin_clave_guias_no_revienta(self):
        resultado = self._llamar({'error': True, 'errorMensaje': 'Token vencido'})
        self.assertTrue(resultado['error'])
        self.assertIn('Token vencido', resultado['mensaje'])

    def test_lista_vacia_es_valida(self):
        """Sin pendientes NO es un error: el importador debe cortar el lote, no fallar."""
        resultado = self._llamar({'guias': []})
        self.assertFalse(resultado['error'])
        self.assertEqual(resultado['guias'], [])

    def test_guias_pasan(self):
        resultado = self._llamar({'guias': [{'numero': 1}]})
        self.assertFalse(resultado['error'])
        self.assertEqual(len(resultado['guias']), 1)


class _Peticion:
    """Solo se necesita .data: el guard responde antes de tocar BD o Holmio."""

    def __init__(self, data):
        self.data = data


class DespachoIdNumericoTests(TestCase):
    """El usuario escribio la placa "WCQ399" en el campo "Despacho".

    Semantica interpola el codigo sin comillas en su consulta, asi que un valor
    no numerico le revienta la API con un DQL ininteligible. Se ataja antes.
    """

    def _llamar(self, despacho_id):
        return RutDespachoViewSet().nuevo_complemento_action(
            _Peticion({'despacho_id': despacho_id}),
        )

    def test_placa_se_rechaza_sin_llamar_al_complemento(self):
        with patch.object(Holmio, 'consumirPost') as consumir:
            respuesta = self._llamar('WCQ399')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('placa', respuesta.data['mensaje'])
        consumir.assert_not_called()

    def test_alfanumerico_se_rechaza(self):
        self.assertEqual(self._llamar('12A34').status_code, 400)

    def test_vacio_sigue_dando_faltan_parametros(self):
        respuesta = self._llamar('')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('Faltan parametros', respuesta.data['mensaje'])

    def test_numerico_con_espacios_pasa_el_guard(self):
        """Se recorta y sigue: el fallo debe venir de Holmio, no del guard."""
        with patch.object(Holmio, 'consumirPost', return_value={'status': 500, 'mensaje': 'x'}) as consumir:
            respuesta = self._llamar('  12345  ')
        self.assertEqual(consumir.call_args[0][0], {'codigo_despacho': '12345'})
        self.assertEqual(respuesta.status_code, 400)
        self.assertNotIn('placa', respuesta.data['mensaje'])
