"""Serializer de despacho/entrega de la API movil v2."""
from rest_framework import serializers

from vertical.models.entrega import VerEntrega


class DespachoMovilSerializer(serializers.ModelSerializer):
    """Resumen del despacho que la app resuelve a partir de un codigo.

    Incluye `schema_name`: el tenant al que pertenece el despacho, que la app
    usa para enrutar las llamadas posteriores al subdominio correcto.
    """

    class Meta:
        model = VerEntrega
        fields = [
            'id', 'fecha', 'peso', 'volumen', 'tiempo', 'tiempo_servicio',
            'tiempo_trayecto', 'visitas', 'visitas_entregadas', 'despacho_id',
            'contenedor_id', 'usuario_id', 'schema_name',
        ]
        read_only_fields = fields
