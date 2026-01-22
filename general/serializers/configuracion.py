from general.models.configuracion import GenConfiguracion
from general.models.empresa import GenEmpresa

from rest_framework import serializers
from decouple import config

class GenConfiguracionSerializador(serializers.ModelSerializer):
    class Meta:
        model = GenConfiguracion
        fields = ['id', 'empresa', 'informacion_factura', 'informacion_factura_superior',         
            'rut_sincronizar_complemento', 
            'rut_rutear_franja', 
            'rut_direccion_origen', 
            'rut_latitud', 
            'rut_longitud',
            'rut_decodificar_direcciones'
        ]   
        select_related_fields = ['empresa']   

class GenConfiguracionRndcSerializador(serializers.ModelSerializer):
    empresa__numero_identificacion = serializers.CharField(source='empresa.numero_identificacion', read_only=True)
    class Meta:
        model = GenConfiguracion
        fields = ['id', 'tte_usuario_rndc', 'tte_clave_rndc', 'tte_numero_poliza', 'tte_fecha_vence_poliza', 'tte_numero_identificacion_aseguradora', 'empresa__numero_identificacion']      
        select_related_fields = ['empresa']           