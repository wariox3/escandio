"""Tests de los payloads interactivos (botones/lista) de WhatsappCliente.

Bloquean la FORMA exacta que espera Meta Cloud API: un typo en el JSON no falla
en tests normales (mockeamos la red) pero sí rompe contra la API real. Acá
verificamos estructura, ids autogenerados y los recortes de longitud que impone
Meta (título botón 20, fila 24, descripción 72, botón lista 20).

Correr: python manage.py test mensajeria.tests_whatsapp_interactivo
"""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from mensajeria.servicios.whatsapp_cliente import WhatsappCliente


def _cliente():
    conexion = SimpleNamespace(id=1, phone_number_id='PNID', access_token_cifrado='x')
    return WhatsappCliente(conexion)


class BotonesPayloadTests(TestCase):

    def _payload(self, telefono, texto, opciones):
        cli = _cliente()
        with patch.object(cli, '_post', return_value={'error': False}) as post:
            cli.enviar_botones(telefono, texto, opciones)
        return post.call_args.args[0]

    def test_estructura_basica(self):
        p = self._payload('573001112233', '¿Qué guía?', [{'titulo': 'Ana'}, {'titulo': 'Juan'}])
        self.assertEqual(p['type'], 'interactive')
        self.assertEqual(p['interactive']['type'], 'button')
        self.assertEqual(p['interactive']['body']['text'], '¿Qué guía?')
        botones = p['interactive']['action']['buttons']
        self.assertEqual([b['reply']['id'] for b in botones], ['op_0', 'op_1'])
        self.assertEqual([b['reply']['title'] for b in botones], ['Ana', 'Juan'])

    def test_max_3_botones(self):
        ops = [{'titulo': f'op{i}'} for i in range(5)]
        p = self._payload('57300', 'x', ops)
        self.assertEqual(len(p['interactive']['action']['buttons']), 3)

    def test_titulo_recortado_a_20(self):
        p = self._payload('57300', 'x', [{'titulo': 'X' * 40}])
        self.assertEqual(len(p['interactive']['action']['buttons'][0]['reply']['title']), 20)

    def test_omite_titulos_vacios(self):
        # Un título vacío/espacios haría que Meta rechace TODO el mensaje: se salta.
        p = self._payload('57300', 'x', [{'titulo': ''}, {'titulo': 'Ok'}, {'titulo': '  '}])
        titulos = [b['reply']['title'] for b in p['interactive']['action']['buttons']]
        self.assertEqual(titulos, ['Ok'])


class ListaPayloadTests(TestCase):

    def _payload(self, **kw):
        cli = _cliente()
        with patch.object(cli, '_post', return_value={'error': False}) as post:
            cli.enviar_lista(**kw)
        return post.call_args.args[0]

    def test_estructura_y_filas(self):
        ops = [{'titulo': f'op {i}', 'descripcion': f'd{i}'} for i in range(4)]
        p = self._payload(telefono='57300', texto='Elegí', boton='Ver guías', opciones=ops)
        self.assertEqual(p['interactive']['type'], 'list')
        self.assertEqual(p['interactive']['action']['button'], 'Ver guías')
        seccion = p['interactive']['action']['sections'][0]
        self.assertEqual([f['id'] for f in seccion['rows']], ['op_0', 'op_1', 'op_2', 'op_3'])
        self.assertEqual(seccion['rows'][0]['description'], 'd0')

    def test_max_10_filas(self):
        ops = [{'titulo': f'op{i}'} for i in range(15)]
        p = self._payload(telefono='57300', texto='x', boton='Ver', opciones=ops)
        self.assertEqual(len(p['interactive']['action']['sections'][0]['rows']), 10)

    def test_sin_descripcion_no_agrega_campo(self):
        p = self._payload(telefono='57300', texto='x', boton='Ver', opciones=[{'titulo': 'op'}])
        self.assertNotIn('description', p['interactive']['action']['sections'][0]['rows'][0])

    def test_recortes_de_longitud(self):
        ops = [{'titulo': 'T' * 40, 'descripcion': 'D' * 100}]
        p = self._payload(telefono='57300', texto='x', boton='B' * 40, opciones=ops)
        fila = p['interactive']['action']['sections'][0]['rows'][0]
        self.assertEqual(len(fila['title']), 24)
        self.assertEqual(len(fila['description']), 72)
        self.assertEqual(len(p['interactive']['action']['button']), 20)
