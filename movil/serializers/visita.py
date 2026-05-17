"""Serializers de visitas de la API movil v2."""
from rest_framework import serializers

from ruteo.models.visita import RutVisita


class VisitaMovilSerializer(serializers.ModelSerializer):
    """Visita tal como la consume la app del conductor (solo lectura)."""
    ciudad_nombre = serializers.CharField(
        source='ciudad.nombre', read_only=True, allow_null=True, default=None,
    )

    class Meta:
        model = RutVisita
        fields = [
            'id', 'numero', 'fecha', 'documento', 'remitente', 'destinatario',
            'destinatario_direccion', 'destinatario_direccion_formato',
            'destinatario_direccion_complemento', 'destinatario_telefono',
            'destinatario_correo', 'ciudad_nombre', 'unidades', 'peso', 'volumen',
            'cobro', 'tarifa', 'latitud', 'longitud', 'orden', 'distancia',
            'observacion', 'cita_inicio', 'cita_fin', 'despacho_id', 'franja_id',
            'fecha_entrega', 'estado_entregado', 'estado_novedad',
            'estado_devolucion', 'estado_despacho',
        ]
        read_only_fields = fields


class EntregaRequestSerializer(serializers.Serializer):
    """Documenta el cuerpo multipart de POST /visitas/{id}/entregar/."""
    fecha_entrega = serializers.CharField(help_text='Formato: YYYY-MM-DD HH:MM')
    datos_adicionales = serializers.CharField(
        required=False, allow_blank=True,
        help_text='JSON con datos de quien recibe (firma, identificacion, etc).',
    )
    imagenes = serializers.ListField(
        child=serializers.ImageField(), required=False,
        help_text='Fotos de evidencia de la entrega.',
    )
    firmas = serializers.ListField(
        child=serializers.ImageField(), required=False,
        help_text='Imagenes de firma del receptor.',
    )
