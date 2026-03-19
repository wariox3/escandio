from django.db import models


class GenApiKey(models.Model):
    nombre = models.CharField(max_length=100)
    clave = models.CharField(max_length=64, unique=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "gen_api_key"

    def __str__(self):
        return self.nombre
