from django.db import models
from ruteo.models.vehiculo import RutVehiculo

class RutFlota(models.Model):
    vehiculo = models.ForeignKey(RutVehiculo, on_delete=models.PROTECT, related_name='flotas_vehiculo_rel')
    prioridad = models.IntegerField(null=True)

    class Meta:
        db_table = "rut_flota"
        ordering = ["-id"]