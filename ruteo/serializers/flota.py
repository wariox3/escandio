from rest_framework import serializers
from ruteo.models.vehiculo import RutVehiculo
from ruteo.models.flota import RutFlota
from ruteo.serializers.franja import RutFranjaSeleccionarSerializador


class RutFlotaSerializador(serializers.HyperlinkedModelSerializer):    
    vehiculo = serializers.PrimaryKeyRelatedField(queryset=RutVehiculo.objects.all())
    class Meta:
        model = RutFlota
        fields = ['id', 'vehiculo', 'prioridad']

    def validate(self, data):
        vehiculo_id = data.get('vehiculo') 
        flotas = RutFlota.objects.filter(
            vehiculo_id=vehiculo_id
        )       
        if self.instance:
            flotas = flotas.exclude(pk=self.instance.pk)

        if flotas.exists():            
            raise serializers.ValidationError({
                "vehiculo": "El vehiculo ya está en la flota."
            })
        return data

    def to_representation(self, instance):      
        vehiculo_placa = ""
        vehiculo_capacidad = 0
        vehiculo_tiempo = 0
        vehiculo_estado_asignado = ""
        vehiculo_prioridad = ""
        vehiculo_franjas = []
        if instance.vehiculo:
            vehiculo = instance.vehiculo 
            vehiculo_placa = instance.vehiculo.placa
            vehiculo_capacidad = instance.vehiculo.capacidad
            vehiculo_tiempo = instance.vehiculo.tiempo
            vehiculo_estado_asignado = instance.vehiculo.estado_asignado    
            vehiculo_prioridad = instance.vehiculo.prioridad
            franjas = vehiculo.franjas.all()
            vehiculo_franjas = RutFranjaSeleccionarSerializador(franjas, many=True).data

        return {
            'id': instance.id,  
            'prioridad': instance.prioridad,
            'vehiculo_id': instance.vehiculo_id,
            'vehiculo_placa': vehiculo_placa,
            'vehiculo_capacidad': vehiculo_capacidad,
            'vehiculo_tiempo': vehiculo_tiempo,
            'vehiculo_estado_asignado' : vehiculo_estado_asignado,
            'vehiculo_prioridad' : vehiculo_prioridad,
            'vehiculo_franjas': vehiculo_franjas
        }
    
