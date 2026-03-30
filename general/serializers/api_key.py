from rest_framework import serializers
from general.models.api_key import GenApiKey
import secrets


class GenApiKeySerializador(serializers.ModelSerializer):
    class Meta:
        model = GenApiKey
        fields = ['id', 'nombre', 'clave', 'activo', 'fecha_creacion']
        read_only_fields = ['clave', 'fecha_creacion']

    def create(self, validated_data):
        validated_data['clave'] = secrets.token_hex(32)
        return super().create(validated_data)
