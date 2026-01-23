from rest_framework import serializers
from contenedor.models import CtnVerificacion

class CtnVerificacionSerializador(serializers.ModelSerializer):
    class Meta:
        model = CtnVerificacion
        fields = ['id', 'token', 'estado_usado', 'vence', 'accion', 'usuario_id', 'contenedor_id', 'usuario_invitado_username']      