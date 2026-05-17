"""Serializer de configuracion de la app movil v2."""
from rest_framework import serializers


class AppConfigSerializer(serializers.Serializer):
    version_minima = serializers.CharField()
    version_actual = serializers.CharField()
    actualizacion_requerida = serializers.BooleanField()
    actualizacion_disponible = serializers.BooleanField()
