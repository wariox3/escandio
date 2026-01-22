from rest_framework import serializers
from general.models.archivo import GenArchivo

class GenArchivoSerializador(serializers.HyperlinkedModelSerializer):          

    class Meta:
        model = GenArchivo
        fields = ['id', 'documento']

    def to_representation(self, instance):        
        return {
            'id': instance.id,
            'fecha': instance.fecha,
            'archivo_tipo_id': instance.archivo_tipo_id,
            'nombre': instance.nombre,
            'tipo': instance.tipo,
            'tamano': instance.tamano,
            'almacenamiento_id': instance.almacenamiento_id,
            'documento_id': instance.documento_id,
            'uuid': instance.uuid                        
        }