from rest_framework import serializers
from contenedor.models import Contenedor, UsuarioContenedor
from contenedor.models import User
from datetime import datetime
from decouple import config

class UsuarioContenedorSerializador(serializers.ModelSerializer):
    usuario__nombre = serializers.CharField(source='usuario.nombre', read_only=True)
    usuario__username = serializers.CharField(source='usuario.username', read_only=True)
    class Meta:
        model = UsuarioContenedor
        fields = ['id', 'usuario', 'usuario__nombre', 'usuario__username' ,'contenedor', 'rol']
        select_related_fields = ['usuario']        


class UsuarioContenedorListaSerializador(serializers.ModelSerializer):
    contenedor__nombre = serializers.CharField(source='contenedor.nombre', read_only=True)
    contenedor__usuarios = serializers.CharField(source='contenedor.usuarios', read_only=True)
    contenedor__imagen = serializers.CharField(source='contenedor.imagen', read_only=True)
    contenedor__schema_name = serializers.CharField(source='contenedor.schema_name', read_only=True)
    class Meta:
        model = UsuarioContenedor
        fields = ['id', 'rol', 'contenedor',
                  'contenedor_id', 
                  'contenedor__nombre', 
                  'contenedor__usuarios',
                  'contenedor__imagen',
                  'contenedor__schema_name',                                
                  'usuario_id']
        select_related_fields = ['contenedor', 'usuario']        


class UsuarioContenedorConfiguracionSerializador(serializers.ModelSerializer):
    usuario__nombre = serializers.CharField(source='usuario.nombre', read_only=True)
    usuario__username = serializers.CharField(source='usuario.username', read_only=True)
    usuario__operacion_id = serializers.IntegerField(source='usuario.operacion_id', read_only=True, allow_null=True)
    usuario__operacion_cargo_id = serializers.IntegerField(source='usuario.operacion_cargo_id', read_only=True, allow_null=True)
    class Meta:
        model = UsuarioContenedor
        fields = ['usuario', 'usuario__nombre', 'usuario__username', 'usuario__operacion_id', 'usuario__operacion_cargo_id']
        select_related_fields = ['usuario']      