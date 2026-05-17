"""Serializers reutilizables de la API movil v2."""
from rest_framework import serializers


class MensajeSerializer(serializers.Serializer):
    mensaje = serializers.CharField()


class IdSerializer(serializers.Serializer):
    id = serializers.IntegerField()


class ErrorSerializer(serializers.Serializer):
    """Envelope de error v2. Solo para documentar el schema."""
    codigo = serializers.IntegerField()
    titulo = serializers.CharField()
    mensaje = serializers.CharField()
