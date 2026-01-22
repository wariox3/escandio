from general.models.configuracion import GenConfiguracion
from general.models.empresa import GenEmpresa

from rest_framework import serializers
from decouple import config

class GenConfiguracionSerializador(serializers.ModelSerializer):
    gen_item_administracion__nombre = serializers.CharField(source='gen_item_administracion.nombre', read_only=True)
    gen_item_imprevisto__nombre = serializers.CharField(source='gen_item_imprevisto.nombre', read_only=True)
    gen_item_utilidad__nombre = serializers.CharField(source='gen_item_utilidad.nombre', read_only=True)
    class Meta:
        model = GenConfiguracion
        fields = ['id', 'empresa', 'informacion_factura', 'informacion_factura_superior', 
            'gen_uvt', 
            'gen_emitir_automaticamente',
            'gen_item_administracion',
            'gen_item_administracion__nombre',
            'gen_item_imprevisto',
            'gen_item_imprevisto__nombre',
            'gen_item_utilidad',
            'gen_item_utilidad__nombre',
            'hum_factor', 
            'hum_salario_minimo', 
            'hum_auxilio_transporte', 
            'hum_entidad_riesgo',
            'pos_documento_tipo', 
            'rut_sincronizar_complemento', 
            'rut_rutear_franja', 
            'rut_direccion_origen', 
            'rut_latitud', 
            'rut_longitud',
            'rut_decodificar_direcciones'
        ]   
        select_related_fields = ['empresa', 'hum_entidad_riesgo', 'pos_documento_tipo', 'gen_item_imprevisto', 'gen_item_administracion', 'gen_item_utilidad']   

class GenConfiguracionRndcSerializador(serializers.ModelSerializer):
    empresa__numero_identificacion = serializers.CharField(source='empresa.numero_identificacion', read_only=True)
    class Meta:
        model = GenConfiguracion
        fields = ['id', 'tte_usuario_rndc', 'tte_clave_rndc', 'tte_numero_poliza', 'tte_fecha_vence_poliza', 'tte_numero_identificacion_aseguradora', 'empresa__numero_identificacion']      
        select_related_fields = ['empresa']           