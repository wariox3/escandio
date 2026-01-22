from rest_framework import serializers
from ruteo.models.novedad import RutNovedad

class RutNovedadSerializador(serializers.ModelSerializer):   
    novedad_tipo__nombre = serializers.CharField(source='novedad_tipo.nombre', read_only=True, allow_null=True, default=None)         
    visita__numero = serializers.IntegerField(source='visita.numero', read_only=True, allow_null=True, default=None)    
    
    class Meta:
        model = RutNovedad
        fields = ['id', 'fecha', 'fecha_solucion', 'fecha_registro', 'descripcion', 'solucion', 'estado_solucion', 'visita', 'visita__numero' ,'novedad_tipo',
                  'novedad_tipo__nombre', 'nuevo_complemento', 'movil_token']
        select_related_fields = ['novedad_tipo']    
    
