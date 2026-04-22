from django.db import models
from contenedor.models import User


class MsjConversacion(models.Model):
    ESTADO_ABIERTA = 'abierta'
    ESTADO_CERRADA = 'cerrada'
    ESTADO_CHOICES = [
        (ESTADO_ABIERTA, 'Abierta'),
        (ESTADO_CERRADA, 'Cerrada'),
    ]

    cliente_telefono = models.CharField(max_length=20, unique=True)
    cliente_nombre = models.CharField(max_length=200, null=True, blank=True)
    visita_id = models.IntegerField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_ABIERTA)
    asignada_a = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='conversaciones_asignadas')
    ultimo_mensaje_fecha = models.DateTimeField(null=True, blank=True)
    no_leidos = models.IntegerField(default=0)
    fecha_ventana_24h = models.DateTimeField(null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "msj_conversacion"
        ordering = ["-ultimo_mensaje_fecha", "-id"]

    def __str__(self):
        return f'{self.cliente_telefono} ({self.estado})'
