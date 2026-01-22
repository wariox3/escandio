from django.db import models
from ruteo.models.despacho import RutDespacho
from ruteo.models.franja import RutFranja
from general.models.ciudad import GenCiudad

class RutVisita(models.Model):
    numero = models.IntegerField(null=True)
    fecha = models.DateTimeField(null=True)  
    fecha_entrega = models.DateTimeField(null=True)  
    documento = models.CharField(max_length=30, null=True)
    remitente = models.CharField(max_length=150, null=True)
    destinatario = models.CharField(max_length=150, default='Destinatario')
    destinatario_direccion = models.CharField(max_length=200, default='')
    destinatario_direccion_formato = models.CharField(max_length=200, null=True, default='')
    destinatario_telefono = models.CharField(max_length=50, null=True, blank=True)
    destinatario_correo = models.CharField(max_length=255, null=True, blank=True)
    unidades = models.FloatField(default=0)
    peso = models.FloatField(default=0)
    volumen = models.FloatField(default=0)
    cobro = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    tiempo_servicio = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    tiempo_trayecto = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    tiempo = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    latitud = models.DecimalField(max_digits=25, decimal_places=15, null=True)
    longitud = models.DecimalField(max_digits=25, decimal_places=15, null=True)
    estado_decodificado = models.BooleanField(null=True, default = None)
    estado_decodificado_alerta = models.BooleanField(default = False)
    estado_franja = models.BooleanField(null=True, default=None)
    estado_despacho = models.BooleanField(default = False)
    estado_entregado = models.BooleanField(default = False)
    estado_entregado_complemento = models.BooleanField(default = False)
    estado_novedad = models.BooleanField(default = False)
    estado_devolucion = models.BooleanField(default = False)
    orden = models.IntegerField(default=0)
    distancia = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    resultados = models.JSONField(null=True, blank=True)
    franja_id = models.IntegerField(null=True)
    franja_codigo = models.CharField(max_length=20, null=True)
    datos_entrega = models.JSONField(null=True, blank=True, default=dict, help_text="Datos de la entrega (nombre, identificación, teléfono, etc.)")    
    despacho = models.ForeignKey(RutDespacho, null=True, on_delete=models.PROTECT, related_name='visitas_despacho_rel')    
    ciudad = models.ForeignKey(GenCiudad, null=True, on_delete=models.PROTECT, default=1, related_name='visitas_ciudad_rel')

    def save(self, *args, **kwargs):        
        self.tiempo = self.tiempo_servicio + self.tiempo_trayecto
        super().save(*args, **kwargs)

    class Meta:
        db_table = "rut_visita"