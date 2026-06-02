from rest_framework import serializers
from contenedor.models import Contenedor
from vertical.models.entrega import VerEntrega

class VerEntregaSerializador(serializers.HyperlinkedModelSerializer):


    class Meta:
        model = VerEntrega
        fields = ['id', 'fecha', 'peso', 'volumen', 'tiempo_servicio', 'tiempo_trayecto', 'tiempo', 'visitas', 'visitas_entregadas',
                  'despacho_id', 'contenedor_id', 'usuario_id', 'schema_name', 'empresa_nombre']


    def to_representation(self, instance):

        return {
            'id': instance.id,
            'fecha': instance.fecha,
            'peso': instance.peso,
            'volumen': instance.volumen,
            'tiempo_servicio': instance.tiempo_servicio,
            'tiempo_trayecto': instance.tiempo_trayecto,
            'tiempo': instance.tiempo,
            'visitas': instance.visitas,
            'visitas_entregadas': instance.visitas_entregadas,
            'despacho_id': instance.despacho_id,
            'contenedor_id':instance.contenedor_id,
            'schema_name': instance.schema_name,
            'usuario_id':instance.usuario_id,
            # Aditivo: nombre comercial de la transportadora duena de la orden
            # (Contenedor.nombre, misma fuente que WhatsApp). Null-safe -> la app
            # cae a prettify(schema_name).
            'empresa_nombre': Contenedor.objects.filter(
                pk=instance.contenedor_id,
            ).values_list('nombre', flat=True).first(),
        }
