"""Serializer de ubicacion de la API movil v2."""
from rest_framework import serializers

from ruteo.models.despacho import RutDespacho
from ruteo.models.ubicacion import RutUbicacion
from ruteo.models.visita import RutVisita


class UbicacionMovilSerializer(serializers.ModelSerializer):
    """Punto de tracking enviado por la app en background."""
    despacho = serializers.PrimaryKeyRelatedField(
        queryset=RutDespacho.objects.all(), required=False, allow_null=True, default=None,
    )
    visita = serializers.PrimaryKeyRelatedField(
        queryset=RutVisita.objects.all(), required=False, allow_null=True, default=None,
    )

    class Meta:
        model = RutUbicacion
        fields = ['id', 'fecha', 'latitud', 'longitud', 'despacho', 'visita', 'detenido']
        read_only_fields = ['id', 'fecha']
