from general.models.empresa import GenEmpresa, GenCiudad
from rest_framework import serializers
from decouple import config

class GenEmpresaSerializador(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = GenEmpresa
        fields = ['id', 'numero_identificacion','digito_verificacion','nombre_corto','direccion','ciudad','telefono','correo',
                  'imagen','contenedor_id','rededoc_id','subdominio']
        
    def to_representation(self, instance):
        ciudad_nombre = ""
        ciudad_estado_nombre = ""
        if instance.ciudad:
            ciudad_nombre = instance.ciudad.nombre        
            if instance.ciudad.estado:
                ciudad_estado_nombre = instance.ciudad.estado.nombre
        tipo_persona_nombre = ""
        if instance.tipo_persona:
            tipo_persona_nombre = instance.tipo_persona.nombre
        identificacion_nombre = ""
        if instance.identificacion:
            identificacion_nombre = instance.identificacion.nombre
        regimen_nombre = ""
        if instance.regimen:
            regimen_nombre = instance.regimen.nombre

        region = config('DO_REGION')
        bucket = config('DO_BUCKET')
        return {
            'id': instance.id,            
            'numero_identificacion': instance.numero_identificacion,
            'identificacion_id': instance.identificacion_id,
            'identificacion_nombre': identificacion_nombre,
            'ciudad_id': instance.ciudad_id,
            'ciudad_nombre': ciudad_nombre,
            'ciudad_estado_nombre': ciudad_estado_nombre,
            'digito_verificacion': instance.digito_verificacion,
            'nombre_corto': instance.nombre_corto,
            'direccion': instance.direccion,
            'telefono': instance.telefono,
            'correo': instance.correo,
            'regimen_id': instance.regimen_id,
            'regimen_nombre': regimen_nombre,
            'tipo_persona_id': instance.tipo_persona_id,
            'tipo_persona_nombre': tipo_persona_nombre,
            'rededoc_id' : instance.rededoc_id,
            'imagen': f"https://{bucket}.{region}.digitaloceanspaces.com/{instance.imagen}",
            'asistente_electronico': instance.asistente_electronico,
            'asistente_predeterminado': instance.asistente_predeterminado
        }   

class GenEmpresaActualizarSerializador(serializers.HyperlinkedModelSerializer):
    ciudad = serializers.PrimaryKeyRelatedField(queryset=GenCiudad.objects.all(), allow_null=True)
    class Meta:
        model = GenEmpresa
        fields = ['nombre_corto', 'direccion', 'correo', 'numero_identificacion', 'digito_verificacion', 'telefono','ciudad', 'identificacion',  'tipo_persona', 'regimen']