from rest_framework import serializers
from ruteo.models.seguimiento import RutSeguimiento

class RutSeguimientoSerializador(serializers.ModelSerializer):    

    class Meta:
        model = RutSeguimiento
        fields = ['id', 'fecha_registro', 'comentario', 'despacho', 'usuario_id']  
    