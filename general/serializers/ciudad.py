from general.models.ciudad import GenCiudad
from rest_framework import serializers

class GenCiudadSerializador(serializers.ModelSerializer):
    estado__nombre = serializers.CharField(source='estado.nombre', read_only=True)
    class Meta:
        model = GenCiudad
        fields = ['id', 'nombre', 'estado__nombre']  
        select_related_fields = ['estado']        