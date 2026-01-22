from rest_framework import serializers
from ruteo.models.despacho import RutDespacho
from ruteo.models.vehiculo import RutVehiculo
from datetime import datetime
from django.utils.timezone import now
from decimal import Decimal

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
                  'vehiculo__capacidad']
        select_related_fields = ['vehiculo']    

class RutDespachoTraficoSerializador(serializers.ModelSerializer):    
    vehiculo__placa = serializers.CharField(source='vehiculo.placa', read_only=True, allow_null=True, default=None)

    class Meta:
        model = RutDespacho
        fields = ['id', 'fecha', 'fecha_salida', 'fecha_ubicacion', 'unidades' ,'peso', 'volumen', 'tiempo', 'tiempo_servicio', 'tiempo_trayecto',
                  'visitas', 'visitas_entregadas', 'visitas_liberadas', 'visitas_novedad', 'entrega_id', 'estado_aprobado', 'estado_terminado', 
                  'estado_anulado', 'latitud', 'longitud', 'codigo_complemento',
                  'vehiculo',
                  'vehiculo__placa']
        select_related_fields = ['vehiculo']
    