"""Tests del cliente LLM agnostico (utilidades/llm.py).

Prueban el mapeo neutral<->Gemini y el parseo de la respuesta, con `requests`
mockeado: sin red ni API key real. Vive en ruteo/ porque utilidades no es app.
"""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from utilidades.llm import ClienteGemini, LLMError, crear_cliente


class MapeoMensajesTests(SimpleTestCase):
    def test_usuario(self):
        self.assertEqual(
            ClienteGemini._map_mensaje({'rol': 'usuario', 'texto': 'hola'}),
            {'role': 'user', 'parts': [{'text': 'hola'}]},
        )

    def test_agente_texto(self):
        self.assertEqual(
            ClienteGemini._map_mensaje({'rol': 'agente', 'texto': 'ok'}),
            {'role': 'model', 'parts': [{'text': 'ok'}]},
        )

    def test_agente_tool_call(self):
        m = ClienteGemini._map_mensaje({'rol': 'agente', 'tool_calls': [{'nombre': 'f', 'args': {'x': 1}}]})
        self.assertEqual(m['role'], 'model')
        self.assertEqual(m['parts'], [{'functionCall': {'name': 'f', 'args': {'x': 1}}}])

    def test_tool_resultado(self):
        m = ClienteGemini._map_mensaje({'rol': 'tool', 'nombre': 'f', 'resultado': {'ok': True}})
        self.assertEqual(
            m,
            {'role': 'user', 'parts': [{'functionResponse': {'name': 'f', 'response': {'ok': True}}}]},
        )

    def test_rol_desconocido_revienta(self):
        with self.assertRaises(LLMError):
            ClienteGemini._map_mensaje({'rol': 'x'})


class ParseoRespuestaTests(SimpleTestCase):
    def test_texto(self):
        data = {'candidates': [{'content': {'parts': [{'text': 'hola conductor'}]}}]}
        r = ClienteGemini._parse(data)
        self.assertEqual(r['texto'], 'hola conductor')
        self.assertEqual(r['tool_calls'], [])

    def test_function_call(self):
        data = {'candidates': [{'content': {'parts': [
            {'functionCall': {'name': 'registrar_novedad', 'args': {'guia': '200002'}}}
        ]}}]}
        r = ClienteGemini._parse(data)
        self.assertIsNone(r['texto'])
        self.assertEqual(r['tool_calls'], [{'nombre': 'registrar_novedad', 'args': {'guia': '200002'}}])

    def test_texto_y_tool_call_juntos(self):
        data = {'candidates': [{'content': {'parts': [
            {'text': 'registro esa'}, {'functionCall': {'name': 'f', 'args': {}}}
        ]}}]}
        r = ClienteGemini._parse(data)
        self.assertEqual(r['texto'], 'registro esa')
        self.assertEqual(len(r['tool_calls']), 1)

    def test_sin_candidates_revienta(self):
        with self.assertRaises(LLMError):
            ClienteGemini._parse({'promptFeedback': {'blockReason': 'SAFETY'}})


class FactoryTests(SimpleTestCase):
    def test_gemini_sin_key_revienta(self):
        with self.assertRaises(LLMError):
            ClienteGemini(api_key='', modelo='m')

    def test_proveedor_no_soportado_revienta(self):
        with self.assertRaises(LLMError):
            crear_cliente(proveedor='inventado')

    def test_crear_gemini_ok(self):
        with patch('utilidades.llm.config', return_value='fake-key'):
            cliente = crear_cliente(proveedor='gemini', modelo='gemini-2.5-flash')
        self.assertIsInstance(cliente, ClienteGemini)
        self.assertEqual(cliente.modelo, 'gemini-2.5-flash')


class GenerarConMockTests(SimpleTestCase):
    def test_generar_arma_cuerpo_y_parsea(self):
        cliente = ClienteGemini(api_key='k', modelo='gemini-2.5-flash')
        fake = MagicMock(status_code=200)
        fake.json.return_value = {'candidates': [{'content': {'parts': [{'text': 'listo'}]}}]}
        with patch('utilidades.llm.requests.post', return_value=fake) as post:
            r = cliente.generar(
                system='sos un agente',
                mensajes=[{'rol': 'usuario', 'texto': 'entregue 4'}],
                herramientas=[{'nombre': 'f', 'descripcion': 'd', 'parametros': {'type': 'object'}}],
            )
        self.assertEqual(r['texto'], 'listo')
        cuerpo = post.call_args.kwargs['json']
        self.assertEqual(cuerpo['system_instruction'], {'parts': [{'text': 'sos un agente'}]})
        self.assertEqual(cuerpo['contents'], [{'role': 'user', 'parts': [{'text': 'entregue 4'}]}])
        self.assertEqual(cuerpo['tools'][0]['function_declarations'][0]['name'], 'f')

    def test_http_error_revienta(self):
        cliente = ClienteGemini(api_key='k', modelo='m')
        fake = MagicMock(status_code=429, text='rate limit')
        with patch('utilidades.llm.requests.post', return_value=fake):
            with self.assertRaises(LLMError):
                cliente.generar(system=None, mensajes=[{'rol': 'usuario', 'texto': 'hi'}])
