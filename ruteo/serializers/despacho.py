from rest_framework import serializers
from ruteo.models.despacho import RutDespacho
from ruteo.models.vehiculo import RutVehiculo
from datetime import datetime
from django.utils.timezone import now
from decimal import Decimal


def _aplicar_contadores_reales(instance, data):
    """Muestra el conteo REAL de visitas cuando el queryset lo anoto (_v_total,
    _v_entregadas, _v_novedad).

    Los campos denormalizados (visitas / visitas_entregadas / visitas_novedad)
    pueden quedar desincronizados de las visitas reales; el conteo anotado es la
    fuente de verdad (coincide con la validacion de 'terminar' y con el detalle).
    Si no viene anotado (p.ej. respuesta de un create), cae al valor almacenado.
    """
    for campo, attr in (
        ('visitas', '_v_total'),
        ('visitas_entregadas', '_v_entregadas'),
        ('visitas_novedad', '_v_novedad'),
    ):
        valor = getattr(instance, attr, None)
        if valor is not None:
            data[campo] = valor


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
                  'conductor_id',
                  'conductor_telefono']
        select_related_fields = ['vehiculo']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['conductor_nombre'] = self._nombre_conductor(instance.conductor_id)
        _aplicar_contadores_reales(instance, data)
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
                  'conductor_id',
                  'cargado_por_id', 'cargado_en']
        select_related_fields = ['vehiculo']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['conductor_nombre'] = self._nombre_conductor(instance.conductor_id)
        # Analitica "cargar por OE (self-service)": quien tomo la orden desde la
        # app. Reusa el mismo cache de nombres (cachea por user id, no solo
        # conductor). conductor_nombre = quien la tiene/entrega hoy.
        data['cargado_por_nombre'] = self._nombre_conductor(instance.cargado_por_id)
        _aplicar_contadores_reales(instance, data)
        return data
