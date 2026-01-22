from django.db import models

class GenComplemento(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=50) 
    instalado = models.BooleanField(default = False)
    estructura_json = models.JSONField(null=True)
    datos_json = models.JSONField(null=True)
    
    class Meta:
        db_table = "gen_complemento"
        ordering = ["-id"]