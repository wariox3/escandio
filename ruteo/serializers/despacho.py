from rest_framework import serializers
from ruteo.models.despacho import RutDespacho
from ruteo.models.vehiculo import RutVehiculo
from datetime import datetime
from django.utils.timezone import now
from decimal import Decimal


class _ConductorNombreMixin:
    """Resuelve conductor_nombre con cache por instancia (request).

    conductor_id no es un FK -> no se puede atravesar con select_related, se
    consulta aparte. Como el serializer (con many=True) se reutiliza para toda
    la lista, cachear en la instancia colapsa el N+1: una consulta por conductor
    UNICO en vez de una por despacho. El cache es por request (DRF crea un
    serializer nuevo por request), seguro en multitenant.
    """

    def _nombre_conductor(self, conductor_id):
        if not conductor_id:
            return None
        cache = self.__dict__.setdefault('_cache_conductores', {})
        if conductor_id not in cache:
            from contenedor.models import User
            usuario = (
                User.objects.filter(pk=conductor_id)
                .only('nombre', 'apellido')
                .first()
            )
            cache[conductor_id] = (
                f'{usuario.nombre or ""} {usuario.apellido or ""}'.strip() or None
                if usuario
                else None
            )
        return cache[conductor_id]


class RutDespachoSerializador(_ConductorNombreMixin, serializers.ModelSerializer):
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
        data['conductor_nombre'] = self._nombre_conductor(instance.conductor_id)
        return data

class RutDespachoTraficoSerializador(_ConductorNombreMixin, serializers.ModelSerializer):
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
        data['conductor_nombre'] = self._nombre_conductor(instance.conductor_id)
        return data
