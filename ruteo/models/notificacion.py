from django.db import models


class RutNotificacion(models.Model):
    fecha = models.DateTimeField(auto_now_add=True)
    despacho_id = models.IntegerField()
    telefono = models.CharField(max_length=20)
    estado_enviado = models.BooleanField(default=False)
    tipo = models.CharField(max_length=20, default='whatsapp')

    class Meta:
        db_table = "rut_notificacion"
        ordering = ["-id"]
