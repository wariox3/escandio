from rest_framework import serializers
from ruteo.models.novedad import RutNovedad

class RutNovedadSerializador(serializers.ModelSerializer):   
    novedad_tipo__nombre = serializers.CharField(source='novedad_tipo.nombre', read_only=True, allow_null=True, default=None)
    visita__numero = serializers.IntegerField(source='visita.numero', read_only=True, allow_null=True, default=None)
    # descripcion OPCIONAL: la app manda "" (string vacio) cuando el conductor no
    # escribe nada, y el novedad_tipo ya categoriza la novedad. Sin este override el
    # ModelSerializer hereda blank=False del modelo y rechaza "" con 400 (codigo 14,
    # "Errores de validacion") -> era la causa de que TODAS las novedades sin
    # descripcion fallaran al sincronizar. allow_blank cubre "", allow_null cubre None.
    descripcion = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = RutNovedad
        fields = ['id', 'fecha', 'fecha_solucion', 'fecha_registro', 'descripcion', 'solucion', 'estado_solucion', 'visita', 'visita__numero' ,'novedad_tipo',
                  'novedad_tipo__nombre', 'nuevo_complemento', 'movil_token']
        select_related_fields = ['novedad_tipo']    
    
