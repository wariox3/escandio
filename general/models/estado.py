from django.db import models
from general.models.pais import GenPais

class GenEstado(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=50)
    codigo = models.CharField(max_length=10, null=True)
    pais = models.ForeignKey(GenPais, on_delete=models.PROTECT)

    class Meta:
        db_table = "gen_estado"
        ordering = ["-id"]