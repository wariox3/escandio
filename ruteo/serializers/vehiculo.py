from rest_framework import serializers
from ruteo.models.vehiculo import RutVehiculo
from ruteo.models.franja import RutFranja

class RutFranjaSimpleSerializador(serializers.ModelSerializer):
    class Meta:
        model = RutFranja
        fields = ['id', 'codigo', 'nombre'] 

class RutVehiculoSerializador(serializers.HyperlinkedModelSerializer):   
    franjas = RutFranjaSimpleSerializador(many=True, read_only=True)
    
    class Meta:
        model = RutVehiculo
        fields = [
            'id', 'placa', 'capacidad', 'tiempo', 
            'estado_activo', 'estado_asignado', 'usuario_app',
            'prioridad', 'franjas'
        ]