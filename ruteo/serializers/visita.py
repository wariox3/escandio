from rest_framework import serializers
from ruteo.models.visita import RutVisita
from ruteo.models.despacho import RutDespacho
from general.models.ciudad import GenCiudad
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

# Precision del campo latitud/longitud (DecimalField decimal_places=15).
_COORD_QUANTIZE = Decimal(1).scaleb(-15)  # 1e-15


def _redondear_coordenada(valor):
    """Redondea una coordenada a 15 decimales (la precision del campo).

    La geocodificacion (Google) puede entregar floats que, al pasar a Decimal,
    traen MAS de 15 decimales por el redondeo binario (p.ej.
    -75.12345678901234567). DecimalField(decimal_places=15) rechaza eso
    ("Asegurese de que no haya mas de 15 decimales") y rompe la fila del import.
    Lo recortamos a 15 decimales (precision sub-milimetrica, sobra para cualquier
    coordenada) ANTES de validar. None/'' pasan igual; un valor no numerico se
    deja para que el serializador reporte el error real.
    """
    if valor is None or valor == '':
        return valor
    try:
        return Decimal(str(valor)).quantize(_COORD_QUANTIZE, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return valor


class RutVisitaSerializador(serializers.ModelSerializer):
    ciudad__nombre = serializers.CharField(source='ciudad.nombre', read_only=True, allow_null=True, default=None)

    def to_internal_value(self, data):
        # Redondear lat/long a la precision del campo ANTES de validar, para que
        # una coordenada geocodificada con >15 decimales no rompa el import.
        if isinstance(data, dict):
            data = data.copy()
            for campo in ('latitud', 'longitud'):
                if campo in data:
                    data[campo] = _redondear_coordenada(data[campo])
        return super().to_internal_value(data)

    def validate(self, data):
        cita_inicio = data.get('cita_inicio', getattr(self.instance, 'cita_inicio', None) if self.instance else None)
        cita_fin = data.get('cita_fin', getattr(self.instance, 'cita_fin', None) if self.instance else None)
        if cita_inicio and not cita_fin:
            raise serializers.ValidationError({'cita_fin': 'Si se define cita_inicio, cita_fin es obligatorio.'})
        if cita_fin and not cita_inicio:
            raise serializers.ValidationError({'cita_inicio': 'Si se define cita_fin, cita_inicio es obligatorio.'})
        if cita_inicio and cita_fin:
            if cita_fin <= cita_inicio:
                raise serializers.ValidationError({'cita_fin': 'cita_fin debe ser mayor que cita_inicio.'})
            inicio_date = cita_inicio.date() if hasattr(cita_inicio, 'date') else cita_inicio
            fin_date = cita_fin.date() if hasattr(cita_fin, 'date') else cita_fin
            if inicio_date != fin_date:
                raise serializers.ValidationError({'cita_fin': 'cita_inicio y cita_fin deben ser del mismo día.'})
        return data

    class Meta:
        model = RutVisita
        fields = ['id', 'numero', 'fecha', 'documento', 'destinatario', 'destinatario_direccion', 'destinatario_direccion_formato',
                  'destinatario_telefono', 'destinatario_correo', 'unidades', 'peso', 'volumen', 'cobro', 'tarifa', 'tiempo', 'tiempo_servicio', 'tiempo_trayecto',
                  'latitud', 'longitud', 'orden', 'distancia', 'ciudad', 'ciudad__nombre' , 'despacho', 'franja_id', 'franja_codigo', 'resultados',
                  'datos_entrega', 'remitente', 'tarifa', 'observacion', 'destinatario_direccion_complemento', 'cita_inicio', 'cita_fin',
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
            'tarifa',
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
            'observacion',
            'destinatario_direccion_complemento',
            'estado_novedad',
            'estado_devolucion',
            'estado_entregado',
            'estado_despacho',
            # La lista tiene columnas 'Decodificado'/'Alerta' y resalta filas con
            # alerta; sin estos campos llegaban undefined y nunca se mostraban.
            'estado_decodificado',
            'estado_decodificado_alerta',
            'cita_inicio',
            'cita_fin'
        ]

class RutVisitaDetalleSerializador(serializers.ModelSerializer):
    ciudad__nombre = serializers.CharField(source='ciudad.nombre', read_only=True, allow_null=True, default=None)

    class Meta:
        model = RutVisita
        fields = ['id', 'numero', 'fecha', 'documento', 'remitente', 'destinatario', 'destinatario_direccion', 'destinatario_direccion_formato',
                  'destinatario_telefono', 'destinatario_correo', 'unidades', 'peso', 'volumen', 'cobro', 'tarifa', 'tiempo', 'tiempo_servicio', 'tiempo_trayecto',
                  'latitud', 'longitud', 'orden', 'distancia', 'ciudad', 'ciudad__nombre' , 'despacho', 'franja_id', 'franja_codigo', 'resultados',
                  'datos_entrega', 'observacion', 'destinatario_direccion_complemento', 'cita_inicio', 'cita_fin',
                  'estado_decodificado', 'estado_novedad', 'estado_devolucion', 'estado_decodificado_alerta',
                  'estado_entregado', 'estado_entregado_complemento', 'estado_despacho']
        select_related_fields = ['despacho', 'ciudad']

class RutVisitaExcelSerializador(serializers.ModelSerializer):
    ciudad__nombre = serializers.CharField(source='ciudad.nombre', read_only=True, allow_null=True, default=None)
    despacho__vehiculo__placa = serializers.CharField(source='despacho.vehiculo.placa', read_only=True, allow_null=True, default=None)

    class Meta:
        model = RutVisita
        fields = [
                    'id', 'numero', 'fecha', 'documento', 'remitente', 'destinatario', 'destinatario_direccion', 'destinatario_direccion_formato',
                  'destinatario_telefono', 'destinatario_correo', 'unidades', 'peso', 'volumen', 'cobro', 'tarifa', 'tiempo', 'tiempo_servicio', 'tiempo_trayecto',
                  'latitud', 'longitud', 'orden', 'distancia', 'ciudad', 'ciudad__nombre' , 'despacho', 'despacho__vehiculo__placa', 'franja_id', 'franja_codigo',
                  'cita_inicio', 'cita_fin',
                  'estado_decodificado',
                  'estado_novedad',
                  'estado_devolucion',
                  'estado_decodificado_alerta',
                  'estado_entregado',
                  'estado_entregado_complemento',
                  'estado_despacho']
        select_related_fields = ['despacho__vehiculo', 'ciudad']

class RutVistaTraficoSerializador(serializers.ModelSerializer):
    class Meta:
        model = RutVisita
        # estado_decodificado(_alerta) y cita_* son necesarios para que el front
        # clasifique bien el badge de estado. Sin ellos llegaban undefined y
        # '!estado_decodificado' marcaba como 'alerta' a TODA visita pendiente.
        # cita_tipo evita marcar como 'cita-vencida' (bloqueante) a una cita
        # preferente vencida, que el front trata distinto a la obligatoria.
        fields = ['id', 'fecha', 'numero', 'documento', 'destinatario', 'destinatario_direccion', 'destinatario_telefono',
                  'estado_entregado', 'estado_novedad', 'unidades',
                  'estado_decodificado', 'estado_decodificado_alerta', 'cita_inicio', 'cita_fin', 'cita_tipo', 'fecha_entrega']

class RutVistaEstadoSerializador(serializers.ModelSerializer):    
    class Meta:
        model = RutVisita
        fields = ['id', 'fecha', 'numero', 'documento', 'estado_despacho', 'estado_entregado', 'estado_novedad', 'estado_devolucion', 'fecha_entrega']