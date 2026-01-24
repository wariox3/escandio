from general.models.empresa import GenEmpresa, GenCiudad
from rest_framework import serializers
from decouple import config

class GenEmpresaSerializador(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = GenEmpresa
        fields = ['id', 'numero_identificacion','digito_verificacion','nombre_corto','direccion','ciudad','telefono','correo',
                  'imagen','contenedor_id','subdominio']
        
    def to_representation(self, instance):
        ciudad_nombre = ""
        ciudad_estado_nombre = ""
        if instance.ciudad:
            ciudad_nombre = instance.ciudad.nombre        
            if instance.ciudad.estado:
                ciudad_estado_nombre = instance.ciudad.estado.nombre

        region = config('DO_REGION')
        bucket = config('DO_BUCKET')
        return {
            'id': instance.id,            
            'numero_identificacion': instance.numero_identificacion,
            'ciudad_id': instance.ciudad_id,
            'ciudad_nombre': ciudad_nombre,
            'ciudad_estado_nombre': ciudad_estado_nombre,
            'digito_verificacion': instance.digito_verificacion,
            'nombre_corto': instance.nombre_corto,
            'direccion': instance.direccion,
            'telefono': instance.telefono,
            'correo': instance.correo,
            'imagen': f"https://{bucket}.{region}.digitaloceanspaces.com/{instance.imagen}"
        }   

class GenEmpresaActualizarSerializador(serializers.HyperlinkedModelSerializer):
    ciudad = serializers.PrimaryKeyRelatedField(queryset=GenCiudad.objects.all(), allow_null=True)
    class Meta:
        model = GenEmpresa
        fields = ['nombre_corto', 'direccion', 'correo', 'numero_identificacion', 'digito_verificacion', 'telefono','ciudad', 'identificacion',  'tipo_persona', 'regimen']