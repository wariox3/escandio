from rest_framework import serializers
from ruteo.models.ubicacion import RutUbicacion
from ruteo.models.despacho import RutDespacho
from ruteo.models.visita import RutVisita

class RutUbicacionSerializador(serializers.HyperlinkedModelSerializer):    
    despacho = serializers.PrimaryKeyRelatedField(queryset=RutDespacho.objects.all(), default=None, allow_null=True)
    visita = serializers.PrimaryKeyRelatedField(queryset=RutVisita.objects.all(), default=None, allow_null=True)
    
    class Meta:
        model = RutUbicacion
        fields = ['id', 'fecha', 'latitud', 'longitud', 'despacho', 'visita', 'usuario_id', 'detenido']

    def to_representation(self, instance):      
        return {
            'id': instance.id,  
            'fecha': instance.fecha,
            'latitud': instance.latitud,
            'longitud': instance.longitud,
            'usuario_id': instance.usuario_id,
            'detenido': instance.detenido
        }
    
class RutUbicacionTraficoSerializador(serializers.ModelSerializer):        
    class Meta:
        model = RutUbicacion
        fields = ['id', 'fecha', 'latitud', 'longitud', 'usuario_id', 'detenido']
