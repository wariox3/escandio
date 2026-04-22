from rest_framework import serializers
from mensajeria.models import MsjConversacion


class MsjConversacionSerializador(serializers.ModelSerializer):
    asignada_a__nombre = serializers.CharField(source='asignada_a.nombre', read_only=True, allow_null=True, default=None)

    class Meta:
        model = MsjConversacion
        fields = [
            'id', 'cliente_telefono', 'cliente_nombre', 'visita_id', 'estado',
            'asignada_a', 'asignada_a__nombre', 'ultimo_mensaje_fecha', 'no_leidos',
            'fecha_ventana_24h', 'fecha', 'fecha_actualizacion',
        ]
        select_related_fields = ['asignada_a']
        read_only_fields = ['ultimo_mensaje_fecha', 'no_leidos', 'fecha_ventana_24h', 'fecha', 'fecha_actualizacion']
