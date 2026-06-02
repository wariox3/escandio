"""Serializer de despacho/entrega de la API movil v2."""
from rest_framework import serializers

from contenedor.models import Contenedor
from vertical.models.entrega import VerEntrega


class DespachoMovilSerializer(serializers.ModelSerializer):
    """Resumen del despacho que la app resuelve a partir de un codigo.

    Incluye `schema_name`: el tenant al que pertenece el despacho, que la app
    usa para enrutar las llamadas posteriores al subdominio correcto.
    """

    # Nombre comercial de la empresa transportadora duena de la orden: el mismo
    # `Contenedor.nombre` que usan las notificaciones WhatsApp (ver
    # ruteo/servicios/notificacion.py). La app lo muestra en el boton de chat con
    # el cliente; si viene null cae a prettify(schema_name) del lado app.
    empresa_nombre = serializers.SerializerMethodField()

    class Meta:
        model = VerEntrega
        fields = [
            'id', 'fecha', 'peso', 'volumen', 'tiempo', 'tiempo_servicio',
            'tiempo_trayecto', 'visitas', 'visitas_entregadas', 'despacho_id',
            'contenedor_id', 'usuario_id', 'schema_name', 'empresa_nombre',
        ]
        read_only_fields = fields

    def get_empresa_nombre(self, instance) -> str | None:
        return Contenedor.objects.filter(
            pk=instance.contenedor_id,
        ).values_list('nombre', flat=True).first()
