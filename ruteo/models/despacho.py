from django.db import models
from ruteo.models.vehiculo import RutVehiculo

class RutDespacho(models.Model):
    fecha = models.DateTimeField(null=True)
    fecha_salida = models.DateTimeField(null=True)
    fecha_ubicacion = models.DateTimeField(null=True)    
    peso = models.FloatField(default=0)
    volumen = models.FloatField(default=0)
    unidades = models.FloatField(default=0)
    tiempo_servicio = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    tiempo_trayecto = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    tiempo = models.DecimalField(max_digits=12, decimal_places=6, default=0)    
    visitas = models.FloatField(default=0)    
    visitas_entregadas = models.FloatField(default=0)
    visitas_liberadas = models.FloatField(default=0)
    visitas_novedad = models.FloatField(default=0)
    estado_aprobado = models.BooleanField(default = False)
    estado_terminado = models.BooleanField(default = False)
    estado_anulado = models.BooleanField(default = False)
    entrega_id = models.IntegerField(null=True)
    codigo_complemento = models.IntegerField(null=True)
    latitud = models.DecimalField(max_digits=25, decimal_places=15, null=True)
    longitud = models.DecimalField(max_digits=25, decimal_places=15, null=True)    
    vehiculo = models.ForeignKey(RutVehiculo, null=True, on_delete=models.PROTECT, related_name='despachos_vehiculo_rel')

    class Meta:
        db_table = "rut_despacho"
        ordering = ["-id"]