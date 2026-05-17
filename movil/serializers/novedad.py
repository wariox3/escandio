"""Serializers de novedades de la API movil v2."""
from rest_framework import serializers

from ruteo.models.novedad_tipo import RutNovedadTipo


class NovedadTipoMovilSerializer(serializers.ModelSerializer):
    class Meta:
        model = RutNovedadTipo
        fields = ['id', 'nombre']
        read_only_fields = fields


class CrearNovedadRequestSerializer(serializers.Serializer):
    """Documenta el cuerpo multipart de POST /novedades/."""
    visita_id = serializers.IntegerField()
    novedad_tipo_id = serializers.IntegerField()
    fecha = serializers.CharField(help_text='Formato: YYYY-MM-DD HH:MM')
    descripcion = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    movil_token = serializers.CharField(
        help_text='Clave de idempotencia generada por la app.',
    )
    imagenes = serializers.ListField(
        child=serializers.ImageField(), required=False,
        help_text='Fotos de evidencia de la novedad.',
    )


class SolucionarNovedadSerializer(serializers.Serializer):
    solucion = serializers.CharField(required=False, allow_blank=True, allow_null=True)
