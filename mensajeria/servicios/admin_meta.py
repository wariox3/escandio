import logging
import requests
from decouple import config

logger = logging.getLogger(__name__)


class AdminMetaServicio:
    """
    Cliente para consultar la WABA administrada centralmente por Rutenio.
    Usa META_ADMIN_WABA_ID y META_ADMIN_ACCESS_TOKEN del .env (globales).
    """

    TIMEOUT_SEGUNDOS = 10

    def __init__(self):
        self.waba_id = config('META_ADMIN_WABA_ID', default='')
        self.access_token = config('META_ADMIN_ACCESS_TOKEN', default='')
        self.api_version = config('META_GRAPH_API_VERSION', default='v21.0')
        self.base_url = f'https://graph.facebook.com/{self.api_version}'

    def _configurado(self):
        return bool(self.waba_id and self.access_token)

    def _headers(self):
        return {'Authorization': f'Bearer {self.access_token}'}

    def listar_numeros(self):
        """Retorna la lista de phone_numbers de la WABA admin."""
        if not self._configurado():
            return {
                'error': True,
                'mensaje': 'META_ADMIN_WABA_ID o META_ADMIN_ACCESS_TOKEN no configurados',
                'data': [],
            }
        url = (
            f'{self.base_url}/{self.waba_id}/phone_numbers'
            '?fields=id,display_phone_number,verified_name,quality_rating,'
            'code_verification_status,platform_type,throughput'
        )
        try:
            r = requests.get(url, headers=self._headers(), timeout=self.TIMEOUT_SEGUNDOS)
            datos = r.json() if r.content else {}
            if r.status_code == 200:
                return {'error': False, 'data': datos.get('data', [])}
            return {
                'error': True,
                'mensaje': datos.get('error', {}).get('message') or f'HTTP {r.status_code}',
                'data': [],
            }
        except requests.RequestException as e:
            logger.error(f'AdminMeta listar_numeros: {e}')
            return {'error': True, 'mensaje': str(e), 'data': []}

    def consultar_numero(self, phone_number_id):
        """Detalle de un phone_number específico."""
        if not self._configurado():
            return {'error': True, 'mensaje': 'Credenciales admin no configuradas'}
        url = (
            f'{self.base_url}/{phone_number_id}'
            '?fields=id,display_phone_number,verified_name,quality_rating,code_verification_status'
        )
        try:
            r = requests.get(url, headers=self._headers(), timeout=self.TIMEOUT_SEGUNDOS)
            datos = r.json() if r.content else {}
            if r.status_code == 200:
                return {'error': False, 'data': datos}
            return {'error': True, 'mensaje': datos.get('error', {}).get('message') or f'HTTP {r.status_code}'}
        except requests.RequestException as e:
            return {'error': True, 'mensaje': str(e)}
