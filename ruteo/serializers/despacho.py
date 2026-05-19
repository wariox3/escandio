from rest_framework import serializers
from ruteo.models.despacho import RutDespacho
from ruteo.models.vehiculo import RutVehiculo
from datetime import datetime
from django.utils.timezone import now
from decimal import Decimal


def _nombre_conductor(conductor_id):
    """Resuelve el nombre del conductor (contenedor.User) por id plano.

    conductor_id no es un FK -> no se puede atravesar con select_related, se
    consulta aparte. Devuelve None si no hay conductor o no existe el usuario.
    """
    if not conductor_id:
        return None
    from contenedor.models import User
    usuario = User.objects.filter(pk=conductor_id).only('nombre', 'apellido').first()
    if not usuario:
        return None
    return f'{usuario.nombre or ""} {usuario.apellido or ""}'.strip() or None


class RutDespachoSerializador(serializers.ModelSerializer):
    vehiculo__placa = serializers.CharField(source='vehiculo.placa', read_only=True, allow_null=True, default=None)
    vehiculo__capacidad = serializers.IntegerField(source='vehiculo.capacidad', read_only=True, allow_null=True, default=None)

    class Meta:
        model = RutDespacho
        fields = ['id', 'fecha', 'fecha_salida', 'fecha_ubicacion', 'unidades' ,'peso', 'volumen', 'tiempo', 'tiempo_servicio', 'tiempo_trayecto',
                  'visitas', 'visitas_entregadas', 'visitas_liberadas', 'visitas_novedad', 'entrega_id', 'estado_aprobado', 'estado_terminado',
                  'codigo_complemento',
                  'vehiculo',
                  'vehiculo__placa' ,
                  'vehiculo__capacidad',
                  'conductor_id']
        select_related_fields = ['vehiculo']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['conductor_nombre'] = _nombre_conductor(instance.conductor_id)
        return data

class RutDespachoTraficoSerializador(serializers.ModelSerializer):
    vehiculo__placa = serializers.CharField(source='vehiculo.placa', read_only=True, allow_null=True, default=None)

    class Meta:
        model = RutDespacho
        fields = ['id', 'fecha', 'fecha_salida', 'fecha_ubicacion', 'unidades' ,'peso', 'volumen', 'tiempo', 'tiempo_servicio', 'tiempo_trayecto',
                  'visitas', 'visitas_entregadas', 'visitas_liberadas', 'visitas_novedad', 'entrega_id', 'estado_aprobado', 'estado_terminado',
                  'estado_anulado', 'latitud', 'longitud', 'codigo_complemento',
                  'vehiculo',
                  'vehiculo__placa',
                  'conductor_id']
        select_related_fields = ['vehiculo']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['conductor_nombre'] = _nombre_conductor(instance.conductor_id)
        return data
