from django.db import models
from vertical.models.entrega import VerEntrega


class VerEntregaDetalle(models.Model):
    entrega = models.ForeignKey(VerEntrega, on_delete=models.CASCADE, related_name='detalles')
    visita_id = models.IntegerField()
    numero = models.IntegerField(null=True)
    documento = models.CharField(max_length=30, null=True)
    destinatario = models.CharField(max_length=150, null=True)
    destinatario_direccion = models.CharField(max_length=200, default='')
    destinatario_telefono = models.CharField(max_length=50, null=True, blank=True)
    unidades = models.FloatField(default=0)
    peso = models.FloatField(default=0)
    volumen = models.FloatField(default=0)
    orden = models.IntegerField(default=0)

    class Meta:
        db_table = "ver_entrega_detalle"
        ordering = ["orden"]
