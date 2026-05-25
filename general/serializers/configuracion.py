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
            'rut_decodificar_direcciones',
            'rut_hora_inicio',
            'rut_whatsapp_habilitado',
            'rut_whatsapp_plantilla_despacho',
            'rut_whatsapp_plantilla_idioma',
            'rut_estrategia_ruteo',
            'rut_cita_tipo_defecto',
            'rut_alerta_parada_activa',
            'rut_alerta_parada_minutos',
            'rut_alerta_parada_radio_metros',
            'rut_alerta_geocerca_activa',
            'rut_limite_complemento',
            'rut_limite_importacion',
            'rut_alertas_intervalo_segundos',
        ]
        select_related_fields = ['empresa']

    # Campos nullable que el frontend a veces manda como "" (string vacio) cuando
    # el usuario nunca configuro la direccion o limpia el ng-select de buscador.
    # DecimalField rechaza "" con "A valid number is required" — coercemos a None
    # antes de la validacion para que pase y se guarde como NULL.
    _CAMPOS_NULLABLE_STRING_VACIO = (
        'rut_direccion_origen',
        'rut_latitud',
        'rut_longitud',
        'rut_whatsapp_plantilla_despacho',
    )

    def to_internal_value(self, data):
        if isinstance(data, dict):
            data = data.copy()
            for campo in self._CAMPOS_NULLABLE_STRING_VACIO:
                if data.get(campo) == '':
                    data[campo] = None
        return super().to_internal_value(data)

class GenConfiguracionRndcSerializador(serializers.ModelSerializer):
    empresa__numero_identificacion = serializers.CharField(source='empresa.numero_identificacion', read_only=True)
    class Meta:
        model = GenConfiguracion
        fields = ['id', 'tte_usuario_rndc', 'tte_clave_rndc', 'tte_numero_poliza', 'tte_fecha_vence_poliza', 'tte_numero_identificacion_aseguradora', 'empresa__numero_identificacion']      
        select_related_fields = ['empresa']           