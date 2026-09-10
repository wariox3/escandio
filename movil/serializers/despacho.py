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

    # El "O_E" que muestra Trafico web es RutDespacho.entrega_id (del TENANT), NO
    # el pk de VerEntrega. Esta serializer corre en el dominio base (public) y su
    # `id` es el pk cross-tenant de ver_entrega, que para varias ordenes NO
    # coincide con el entrega_id que ve el despachador. Se lee entrega_id en el
    # schema del tenant del despacho para que la app muestre EXACTAMENTE el mismo
    # numero (el O_E) que Trafico.
    orden_entrega = serializers.SerializerMethodField()

    class Meta:
        model = VerEntrega
        fields = [
            'id', 'fecha', 'peso', 'volumen', 'tiempo', 'tiempo_servicio',
            'tiempo_trayecto', 'visitas', 'visitas_entregadas', 'despacho_id',
            'codigo_complemento', 'orden_entrega',
            'contenedor_id', 'usuario_id', 'schema_name', 'empresa_nombre',
        ]
        read_only_fields = fields

    def get_empresa_nombre(self, instance) -> str | None:
        return Contenedor.objects.filter(
            pk=instance.contenedor_id,
        ).values_list('nombre', flat=True).first()

    def get_orden_entrega(self, instance) -> int | None:
        if not instance.schema_name or not instance.despacho_id:
            return None
        # schema_context es context manager: restaura el schema anterior al salir
        # (no deja la conexion "leakeada" en el tenant). RutDespacho es tenant-only
        # -> hay que entrar al schema del despacho para leerlo.
        from django_tenants.utils import schema_context
        from ruteo.models.despacho import RutDespacho
        try:
            with schema_context(instance.schema_name):
                return (
                    RutDespacho.objects
                    .filter(pk=instance.despacho_id)
                    .values_list('entrega_id', flat=True)
                    .first()
                )
        except Exception:
            return None
