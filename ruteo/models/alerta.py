from django.db import models
from ruteo.models.despacho import RutDespacho
from ruteo.models.visita import RutVisita

ALERTA_TIPO_CHOICES = [
    ('parada_prolongada', 'Parada prolongada'),
    ('fuera_geocerca', 'Fuera de geocerca'),
]


class RutAlerta(models.Model):
    fecha = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(max_length=30, choices=ALERTA_TIPO_CHOICES)
    mensaje = models.CharField(max_length=255, null=True, blank=True)
    despacho = models.ForeignKey(RutDespacho, null=True, on_delete=models.CASCADE, related_name='alertas_despacho_rel')
    visita = models.ForeignKey(RutVisita, null=True, on_delete=models.SET_NULL, related_name='alertas_visita_rel')
    usuario_id = models.IntegerField(null=True)
    latitud = models.DecimalField(max_digits=25, decimal_places=15, null=True)
    longitud = models.DecimalField(max_digits=25, decimal_places=15, null=True)
    duracion_minutos = models.IntegerField(null=True)
    leida = models.BooleanField(default=False)
    fecha_leida = models.DateTimeField(null=True)

    class Meta:
        db_table = "rut_alerta"
        ordering = ["-id"]
