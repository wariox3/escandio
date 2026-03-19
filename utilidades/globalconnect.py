import requests
import json
from decouple import config
import logging

logger = logging.getLogger(__name__)


class GlobalConnect():

    def __init__(self):
        self.dominio = config('GLOBALCONNECT_DOMINIO', default='')
        self.token_usuario = config('GLOBALCONNECT_TOKEN_USUARIO', default='')
        self.token_proyecto = config('GLOBALCONNECT_TOKEN_PROYECTO', default='')

    def _headers(self):
        return {
            'Authorization': f'Bearer {self.token_usuario}',
            'Content-Type': 'application/json'
        }

    def consultar_plantillas(self):
        url = f'{self.dominio}/api/plantillas/{self.token_proyecto}'
        try:
            response = requests.get(url, headers=self._headers())
            if response.status_code == 200:
                datos = response.json()
                return {'error': False, 'data': datos.get('data', []), 'cuentas': datos.get('cuentas', [])}
            else:
                return {'error': True, 'mensaje': f'Error al consultar plantillas: {response.status_code}'}
        except Exception as e:
            logger.error(f'GlobalConnect consultar_plantillas: {e}')
            return {'error': True, 'mensaje': str(e)}

    def enviar_plantilla(self, id_plantilla, destino, variables=None):
        url = f'{self.dominio}/api/envio-plantilla/{self.token_proyecto}'
        datos = {
            'id_plantilla': id_plantilla,
            'destino': destino,
        }
        if variables:
            datos['variables'] = variables
        try:
            response = requests.post(url, data=json.dumps(datos), headers=self._headers())
            resp = response.json()
            if response.status_code == 200:
                return {
                    'error': False,
                    'id': resp.get('id'),
                    'response_meta': resp.get('response_meta')
                }
            else:
                return {'error': True, 'mensaje': f'Error al enviar plantilla: {response.status_code}', 'detalle': resp}
        except Exception as e:
            logger.error(f'GlobalConnect enviar_plantilla a {destino}: {e}')
            return {'error': True, 'mensaje': str(e)}

    def consultar_cuentas_sms(self):
        url = f'{self.dominio}/api/cuentas-sms/{self.token_proyecto}'
        try:
            response = requests.get(url, headers=self._headers())
            if response.status_code == 200:
                datos = response.json()
                return {'error': False, 'data': datos.get('data', [])}
            else:
                return {'error': True, 'mensaje': f'Error al consultar cuentas SMS: {response.status_code}'}
        except Exception as e:
            logger.error(f'GlobalConnect consultar_cuentas_sms: {e}')
            return {'error': True, 'mensaje': str(e)}

    def enviar_sms(self, id_cuenta, destino, mensaje):
        url = f'{self.dominio}/api/envio-sms/{self.token_proyecto}'
        datos = {
            'id_cuenta': id_cuenta,
            'destino': destino,
            'mensaje': mensaje,
        }
        try:
            response = requests.post(url, data=json.dumps(datos), headers=self._headers())
            resp = response.json()
            if response.status_code == 200:
                return {'error': False, 'id': resp.get('id'), 'response': resp.get('response')}
            else:
                return {'error': True, 'mensaje': f'Error al enviar SMS: {response.status_code}', 'detalle': resp}
        except Exception as e:
            logger.error(f'GlobalConnect enviar_sms a {destino}: {e}')
            return {'error': True, 'mensaje': str(e)}
