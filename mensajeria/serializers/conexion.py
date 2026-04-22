from rest_framework import serializers
from contenedor.models import CtnWhatsappConexion


class CtnWhatsappConexionSerializador(serializers.ModelSerializer):
    """Lectura: nunca expone access_token ni app_secret cifrados."""
    access_token = serializers.CharField(write_only=True, required=False, allow_blank=False)
    app_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = CtnWhatsappConexion
        fields = [
            'id', 'phone_number_id', 'waba_id', 'display_phone_number', 'verified_name',
            'estado', 'error_mensaje', 'verify_token',
            'fecha_conexion', 'fecha_actualizacion',
            'access_token', 'app_secret',
        ]
        read_only_fields = [
            'display_phone_number', 'verified_name', 'estado', 'error_mensaje',
            'fecha_conexion', 'fecha_actualizacion',
        ]
