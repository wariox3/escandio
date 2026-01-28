from rest_framework import serializers
from contenedor.models import CtnDireccion

class CtnDireccionSerializador(serializers.ModelSerializer):
    class Meta:
        model = CtnDireccion
        fields = ['id', 'direccion']      