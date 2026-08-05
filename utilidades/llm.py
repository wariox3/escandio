"""Cliente LLM agnostico del proveedor, para el agente de conductores.

Interfaz minima de tool-use que usa el agente:

    cliente = crear_cliente()
    r = cliente.generar(system, mensajes, herramientas)
    # r = {'texto': str|None, 'tool_calls': [{'nombre','args'}], 'raw': dict}

Hoy implementa Gemini (free tier del piloto). Agregar Anthropic/OpenAI = otra
subclase con el mismo contrato, sin tocar el agente.

Formato NEUTRAL de mensajes (lo que arma el agente, independiente del proveedor):
    {'rol': 'usuario', 'texto': str}
    {'rol': 'agente',  'texto': str|None, 'tool_calls': [{'nombre','args'}]|None}
    {'rol': 'tool',    'nombre': str, 'resultado': dict}

Formato NEUTRAL de herramientas:
    {'nombre': str, 'descripcion': str, 'parametros': <JSON Schema del objeto args>}
"""
import logging

import requests
from decouple import config

logger = logging.getLogger(__name__)

TIMEOUT_SEG = 30


class LLMError(Exception):
    """Fallo al hablar con el proveedor LLM (red, credenciales, respuesta rara)."""


class ClienteLLM:
    """Contrato que usa el agente. No instanciar directo: usar crear_cliente()."""

    def generar(self, system, mensajes, herramientas=None):
        raise NotImplementedError


class ClienteGemini(ClienteLLM):
    """Gemini (Google) via generateContent. Function-calling nativo."""

    BASE = 'https://generativelanguage.googleapis.com/v1beta/models'

    def __init__(self, api_key, modelo):
        if not api_key:
            raise LLMError('Falta GEMINI_API_KEY para el proveedor gemini')
        self.api_key = api_key
        self.modelo = modelo

    def generar(self, system, mensajes, herramientas=None):
        cuerpo = {'contents': [self._map_mensaje(m) for m in mensajes]}
        if system:
            cuerpo['system_instruction'] = {'parts': [{'text': system}]}
        if herramientas:
            cuerpo['tools'] = [{
                'function_declarations': [self._map_herramienta(h) for h in herramientas]
            }]
        url = f'{self.BASE}/{self.modelo}:generateContent?key={self.api_key}'
        try:
            resp = requests.post(url, json=cuerpo, timeout=TIMEOUT_SEG)
        except requests.RequestException as e:
            raise LLMError(f'Fallo la llamada a Gemini: {e}') from e
        if resp.status_code != 200:
            raise LLMError(f'Gemini HTTP {resp.status_code}: {resp.text[:300]}')
        return self._parse(resp.json())

    # -- neutral -> Gemini --
    @staticmethod
    def _map_mensaje(m):
        rol = m.get('rol')
        if rol == 'usuario':
            return {'role': 'user', 'parts': [{'text': m.get('texto') or ''}]}
        if rol == 'agente':
            partes = []
            if m.get('texto'):
                partes.append({'text': m['texto']})
            for tc in (m.get('tool_calls') or []):
                fc = {'name': tc['nombre'], 'args': tc.get('args') or {}}
                if tc.get('_id'):
                    fc['id'] = tc['_id']
                parte = {'functionCall': fc}
                # Gemini 3.x exige devolver el thought_signature que vino con el
                # functionCall; si no, rechaza el turno siguiente (HTTP 400).
                if tc.get('_firma'):
                    parte['thoughtSignature'] = tc['_firma']
                partes.append(parte)
            return {'role': 'model', 'parts': partes or [{'text': ''}]}
        if rol == 'tool':
            fr = {'name': m['nombre'], 'response': m.get('resultado') or {}}
            if m.get('_id'):
                fr['id'] = m['_id']
            return {'role': 'user', 'parts': [{'functionResponse': fr}]}
        raise LLMError(f'rol de mensaje desconocido: {rol!r}')

    @staticmethod
    def _map_herramienta(h):
        d = {'name': h['nombre'], 'description': h.get('descripcion', '')}
        if h.get('parametros'):
            d['parameters'] = h['parametros']
        return d

    # -- Gemini -> neutral --
    @staticmethod
    def _parse(data):
        candidatos = data.get('candidates') or []
        if not candidatos:
            # Sin candidates suele ser bloqueo por seguridad o prompt invalido.
            raise LLMError(f'Gemini no devolvio candidates: {str(data)[:300]}')
        partes = ((candidatos[0].get('content') or {}).get('parts')) or []
        texto = None
        tool_calls = []
        for p in partes:
            if p.get('text'):
                texto = (texto or '') + p['text']
            fc = p.get('functionCall')
            if fc:
                tc = {'nombre': fc.get('name'), 'args': fc.get('args') or {}}
                if fc.get('id'):
                    tc['_id'] = fc['id']
                # thought_signature viene a NIVEL de parte; hay que reenviarlo.
                if p.get('thoughtSignature'):
                    tc['_firma'] = p['thoughtSignature']
                tool_calls.append(tc)
        return {'texto': texto, 'tool_calls': tool_calls, 'raw': data}


def crear_cliente(proveedor=None, modelo=None):
    """Factory. Lee LLM_PROVEEDOR / LLM_MODELO / GEMINI_API_KEY de la config."""
    proveedor = (proveedor or config('LLM_PROVEEDOR', default='gemini')).lower()
    if proveedor == 'gemini':
        return ClienteGemini(
            api_key=config('GEMINI_API_KEY', default=''),
            modelo=modelo or config('LLM_MODELO', default='gemini-flash-latest'),
        )
    raise LLMError(f'Proveedor LLM no soportado: {proveedor!r}')
