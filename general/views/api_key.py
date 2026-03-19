from rest_framework import viewsets, permissions
from general.models.api_key import GenApiKey
from general.serializers.api_key import GenApiKeySerializador


class ApiKeyViewSet(viewsets.ModelViewSet):
    queryset = GenApiKey.objects.all()
    serializer_class = GenApiKeySerializador
    permission_classes = [permissions.IsAuthenticated]
