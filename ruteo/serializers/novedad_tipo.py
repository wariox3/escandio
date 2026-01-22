from ruteo.models.novedad_tipo import RutNovedadTipo
from rest_framework import serializers

class RutNovedadTipoSerializador(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = RutNovedadTipo
        fields = ['id', 'nombre']  
        
    def to_representation(self, instance):
        return {
            'id': instance.id,            
            'nombre': instance.nombre
        }
     
class RutNovedadTipoListaAutocompletarSerializador(serializers.HyperlinkedModelSerializer):
    
    class Meta:
        model = RutNovedadTipo

    def to_representation(self, instance):
        return {
            'id': instance.id,            
            'nombre': instance.nombre
        }

class RutNovedadTipoListaBuscarSerializador(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = RutNovedadTipo 
        
    def to_representation(self, instance):
        return {
            'id': instance.id,                        
            'nombre': instance.nombre
        }    