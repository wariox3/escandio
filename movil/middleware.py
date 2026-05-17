"""Middleware de la API movil v2.

Expone la version de la app (header X-App-Version) en request.app_version y
registra la version en cada login v2. Sirve para medir la adopcion de la nueva
app y decidir cuando apagar el legacy v1.6.4.
"""
import logging

logger = logging.getLogger('movil.version')


class VersionAppMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/v2/'):
            request.app_version = request.headers.get('X-App-Version', '')
            # Solo se registra el login: un evento por sesion, sin ruido.
            if request.path == '/api/v2/auth/login/' and request.method == 'POST':
                logger.info(
                    'login app movil v2 version=%s',
                    request.app_version or 'desconocida',
                )
        return self.get_response(request)
