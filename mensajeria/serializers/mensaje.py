from rest_framework import serializers
from mensajeria.models import MsjMensaje


class MsjMensajeSerializador(serializers.ModelSerializer):
    enviado_por__nombre = serializers.CharField(source='enviado_por.nombre', read_only=True, allow_null=True, default=None)

    class Meta:
        model = MsjMensaje
        fields = [
            'id', 'conversacion', 'direccion', 'tipo', 'contenido',
            'whatsapp_message_id', 'estado', 'error_mensaje',
            'media_url', 'media_caption',
            'enviado_por', 'enviado_por__nombre', 'fecha',
        ]
        read_only_fields = [
            'whatsapp_message_id', 'estado', 'error_mensaje',
            'enviado_por', 'enviado_por__nombre', 'fecha',
        ]
