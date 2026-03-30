from rest_framework.permissions import BasePermission
from general.models.api_key import GenApiKey


class TieneApiKey(BasePermission):
    message = 'API Key inválida o no proporcionada.'

    def has_permission(self, request, view):
        clave = request.headers.get('X-Api-Key')
        if not clave:
            return False
        api_key = GenApiKey.objects.filter(clave=clave, activo=True).first()
        if not api_key:
            return False
        request.api_key = api_key
        return True
