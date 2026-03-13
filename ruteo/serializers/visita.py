from rest_framework import serializers
from ruteo.models.visita import RutVisita
from ruteo.models.despacho import RutDespacho
from general.models.ciudad import GenCiudad

class RutVisitaSerializador(serializers.ModelSerializer):
    ciudad__nombre = serializers.CharField(source='ciudad.nombre', read_only=True, allow_null=True, default=None)

    def validate(self, data):
        cita_inicio = data.get('cita_inicio')
        cita_fin = data.get('cita_fin')
        if cita_inicio and not cita_fin:
            raise serializers.ValidationError({'cita_fin': 'Si se define cita_inicio, cita_fin es obligatorio.'})
        if cita_fin and not cita_inicio:
            raise serializers.ValidationError({'cita_inicio': 'Si se define cita_fin, cita_inicio es obligatorio.'})
        if cita_inicio and cita_fin and cita_fin <= cita_inicio:
            raise serializers.ValidationError({'cita_fin': 'cita_fin debe ser mayor que cita_inicio.'})
        return data

    class Meta:
        model = RutVisita
        fields = ['id', 'numero', 'fecha', 'documento', 'destinatario', 'destinatario_direccion', 'destinatario_direccion_formato',
                  'destinatario_telefono', 'destinatario_correo', 'unidades', 'peso', 'volumen', 'cobro', 'tiempo', 'tiempo_servicio', 'tiempo_trayecto',
                  'latitud', 'longitud', 'orden', 'distancia', 'ciudad', 'ciudad__nombre' , 'despacho', 'franja_id', 'franja_codigo', 'resultados',
                  'datos_entrega', 'remitente', 'cobro', 'cita_inicio', 'cita_fin',
                  'estado_decodificado', 'estado_novedad', 'estado_devolucion', 'estado_decodificado_alerta',
                  'estado_entregado', 'estado_entregado_complemento', 'estado_despacho']
        select_related_fields = ['despacho', 'ciudad']

class RutVistaListaSerializador(serializers.ModelSerializer):    
    class Meta:
        model = RutVisita
        fields = [
            'id', 
            'numero', 
            'fecha', 
            'documento', 
            'remitente',
            'destinatario', 
            'destinatario_direccion', 
            'destinatario_direccion_formato', 
            'destinatario_telefono', 
            'destinatario_correo', 
            'unidades',
            'peso', 
            'volumen', 
            'cobro', 
            'tiempo', 
            'tiempo_servicio', 
            'tiempo_trayecto',
            'latitud', 
            'longitud', 
            'orden', 
            'distancia', 
            'despacho_id',
            'franja_id', 
            'franja_codigo',
            'estado_novedad',
            'estado_devolucion',
            'estado_entregado',
            'estado_despacho',
            'cita_inicio',
            'cita_fin'
        ]

class RutVisitaDetalleSerializador(serializers.ModelSerializer):    
    ciudad__nombre = serializers.CharField(source='ciudad.nombre', read_only=True, allow_null=True, default=None)
    
    class Meta:
        model = RutVisita
        fields = ['id', 'numero', 'fecha', 'documento', 'remitente', 'destinatario', 'destinatario_direccion', 'destinatario_direccion_formato',
                  'destinatario_telefono', 'destinatario_correo', 'unidades', 'peso', 'volumen', 'cobro', 'tiempo', 'tiempo_servicio', 'tiempo_trayecto',
                  'latitud', 'longitud', 'orden', 'distancia', 'ciudad', 'ciudad__nombre' , 'despacho', 'franja_id', 'franja_codigo', 'resultados',
                  'datos_entrega', 'cita_inicio', 'cita_fin',
                  'estado_decodificado', 'estado_novedad', 'estado_devolucion', 'estado_decodificado_alerta',
                  'estado_entregado', 'estado_entregado_complemento', 'estado_despacho']
        select_related_fields = ['despacho', 'ciudad']

class RutVisitaExcelSerializador(serializers.ModelSerializer):    
    ciudad__nombre = serializers.CharField(source='ciudad.nombre', read_only=True, allow_null=True, default=None)
    
    class Meta:
        model = RutVisita
        fields = [
                    'id', 'numero', 'fecha', 'documento', 'remitente', 'destinatario', 'destinatario_direccion', 'destinatario_direccion_formato', 
                  'destinatario_telefono', 'destinatario_correo', 'unidades', 'peso', 'volumen', 'cobro', 'tiempo', 'tiempo_servicio', 'tiempo_trayecto',
                  'latitud', 'longitud', 'orden', 'distancia', 'ciudad', 'ciudad__nombre' , 'despacho', 'franja_id', 'franja_codigo',                  
                  'cita_inicio', 'cita_fin',
                  'estado_decodificado',
                  'estado_novedad',
                  'estado_devolucion',
                  'estado_decodificado_alerta',
                  'estado_entregado',
                  'estado_entregado_complemento',
                  'estado_despacho']
        select_related_fields = ['despacho', 'ciudad']

class RutVistaTraficoSerializador(serializers.ModelSerializer):    
    class Meta:
        model = RutVisita
        fields = ['id', 'fecha', 'numero', 'documento', 'destinatario', 'destinatario_direccion', 'destinatario_telefono', 'estado_entregado', 'estado_novedad', 'unidades']

class RutVistaEstadoSerializador(serializers.ModelSerializer):    
    class Meta:
        model = RutVisita
        fields = ['id', 'fecha', 'numero', 'documento', 'estado_despacho', 'estado_entregado', 'estado_novedad', 'estado_devolucion', 'fecha_entrega']