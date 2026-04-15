from rest_framework import serializers
from ruteo.models.alerta import RutAlerta


class RutAlertaSerializador(serializers.ModelSerializer):
    despacho__id = serializers.IntegerField(source='despacho.id', read_only=True, allow_null=True, default=None)
    despacho__vehiculo__placa = serializers.CharField(source='despacho.vehiculo.placa', read_only=True, allow_null=True, default=None)
    visita__numero = serializers.IntegerField(source='visita.numero', read_only=True, allow_null=True, default=None)
    visita__destinatario = serializers.CharField(source='visita.destinatario', read_only=True, allow_null=True, default=None)

    class Meta:
        model = RutAlerta
        fields = [
            'id', 'fecha', 'tipo', 'mensaje', 'despacho', 'despacho__id',
            'despacho__vehiculo__placa', 'visita', 'visita__numero', 'visita__destinatario',
            'usuario_id', 'latitud', 'longitud', 'duracion_minutos', 'leida', 'fecha_leida',
        ]
        select_related_fields = ['despacho', 'despacho__vehiculo', 'visita']
