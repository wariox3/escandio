from django.db import models

class RutNovedadTipo(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=60)
    
    class Meta:
        db_table = "rut_novedad_tipo"
        ordering = ["-id"]