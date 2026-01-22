from rest_framework import serializers
from ruteo.models.franja import RutFranja


class RutFranjaSerializador(serializers.HyperlinkedModelSerializer):    
    class Meta:
        model = RutFranja
        fields = ['id', 'codigo', 'nombre', 'color', 'coordenadas']

    def to_representation(self, instance):        
        return {
            'id': instance.id,  
            'codigo': instance.codigo,
            'nombre': instance.nombre,
            'color': instance.color,
            'coordenadas': instance.coordenadas
        }
    
class RutFranjaSeleccionarSerializador(serializers.ModelSerializer):    
    class Meta:
        model = RutFranja
        fields = ['id', 'codigo', 'nombre']
 
