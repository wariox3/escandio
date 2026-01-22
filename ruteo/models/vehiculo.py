from django.db import models
from ruteo.models.franja import RutFranja

franjas = models.ManyToManyField(RutFranja, related_name='vehiculos')

class RutVehiculo(models.Model):
    placa = models.CharField(max_length=10, unique=True, error_messages={'unique': ('Ya existe un vehículo registrado con esta placa.'),})
    capacidad = models.FloatField(default=0)
    tiempo = models.FloatField(default=0)
    latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True)
    estado_activo = models.BooleanField(default=False)
    estado_asignado = models.BooleanField(default=False)
    franjas = models.ManyToManyField(RutFranja)
    usuario_app = models.CharField(max_length=255, null=True)
    prioridad = models.IntegerField(null=True)

    class Meta:
        db_table = "rut_vehiculo"
        ordering = ["-id"]