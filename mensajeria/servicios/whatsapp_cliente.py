import logging
import requests
from decouple import config
from .cifrado import CifradoServicio

logger = logging.getLogger(__name__)


class WhatsappCliente:
    """
    Cliente para Meta WhatsApp Cloud API (graph.facebook.com).
    Recibe una instancia de CtnWhatsappConexion (con access_token cifrado)
    y expone los métodos de envío.
    """

    TIMEOUT_SEGUNDOS = 10

    def __init__(self, conexion):
        self.conexion = conexion
        self.api_version = config('META_GRAPH_API_VERSION', default='v21.0')
        self.base_url = f'https://graph.facebook.com/{self.api_version}'
        self._access_token = None

    def _obtener_token(self):
        if self._access_token is None:
            self._access_token = CifradoServicio.descifrar(self.conexion.access_token_cifrado)
        return self._access_token

    def _headers(self):
        return {
            'Authorization': f'Bearer {self._obtener_token()}',
            'Content-Type': 'application/json',
        }

    def _endpoint_mensajes(self):
        return f'{self.base_url}/{self.conexion.phone_number_id}/messages'

    def _post(self, payload):
        try:
            respuesta = requests.post(
                self._endpoint_mensajes(),
                json=payload,
                headers=self._headers(),
                timeout=self.TIMEOUT_SEGUNDOS,
            )
            datos = respuesta.json() if respuesta.content else {}
            if respuesta.status_code == 200:
                message_id = None
                mensajes = datos.get('messages') or []
                if mensajes:
                    message_id = mensajes[0].get('id')
                return {'error': False, 'message_id': message_id, 'raw': datos}
            return {
                'error': True,
                'mensaje': datos.get('error', {}).get('message') or f'HTTP {respuesta.status_code}',
                'codigo': datos.get('error', {}).get('code'),
                'raw': datos,
            }
        except requests.Timeout:
            logger.error(f'Whatsapp timeout enviando a phone_number_id={self.conexion.phone_number_id}')
            return {'error': True, 'mensaje': 'Timeout al contactar Meta Graph API'}
        except requests.RequestException as e:
            logger.error(f'Whatsapp request error: {e}')
            return {'error': True, 'mensaje': str(e)}

    def enviar_texto(self, telefono, texto):
        payload = {
            'messaging_product': 'whatsapp',
            'to': telefono,
            'type': 'text',
            'text': {'body': texto, 'preview_url': False},
        }
        return self._post(payload)

    def enviar_imagen(self, telefono, url_imagen, caption=None):
        imagen = {'link': url_imagen}
        if caption:
            imagen['caption'] = caption
        payload = {
            'messaging_product': 'whatsapp',
            'to': telefono,
            'type': 'image',
            'image': imagen,
        }
        return self._post(payload)

    def enviar_plantilla(self, telefono, nombre_plantilla, idioma='es', variables=None):
        plantilla = {
            'name': nombre_plantilla,
            'language': {'code': idioma},
        }
        if variables:
            plantilla['components'] = [{
                'type': 'body',
                'parameters': [{'type': 'text', 'text': str(v)} for v in variables],
            }]
        payload = {
            'messaging_product': 'whatsapp',
            'to': telefono,
            'type': 'template',
            'template': plantilla,
        }
        return self._post(payload)

    def marcar_leido(self, whatsapp_message_id):
        payload = {
            'messaging_product': 'whatsapp',
            'status': 'read',
            'message_id': whatsapp_message_id,
        }
        return self._post(payload)

    def consultar_numero(self):
        """Valida credenciales consultando el phone_number_id."""
        url = f'{self.base_url}/{self.conexion.phone_number_id}'
        try:
            respuesta = requests.get(url, headers=self._headers(), timeout=self.TIMEOUT_SEGUNDOS)
            datos = respuesta.json() if respuesta.content else {}
            if respuesta.status_code == 200:
                return {'error': False, 'data': datos}
            return {'error': True, 'mensaje': datos.get('error', {}).get('message') or f'HTTP {respuesta.status_code}'}
        except requests.RequestException as e:
            return {'error': True, 'mensaje': str(e)}
