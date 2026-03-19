from rest_framework.permissions import BasePermission
from general.models.api_key import GenApiKey


class TieneApiKey(BasePermission):
    message = 'API Key inválida o no proporcionada.'

    def has_permission(self, request, view):
        clave = request.headers.get('X-Api-Key')
        if not clave:
            return False
        return GenApiKey.objects.filter(clave=clave, activo=True).exists()
