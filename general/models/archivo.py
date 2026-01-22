from django.db import models

class GenArchivo(models.Model):    
    archivo_tipo_id = models.IntegerField(default=1) #1-General 2-Entrega 3-Firma
    fecha = models.DateTimeField(auto_now_add=True)    
    nombre = models.CharField(max_length=500)    
    tipo = models.CharField(max_length=100)
    tamano = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    almacenamiento_id = models.CharField(max_length=255)
    uuid = models.CharField(max_length=100, null=True)
    codigo = models.IntegerField(null=True)
    modelo = models.CharField(max_length=100, null=True)
    url = models.CharField(max_length=255, null=True)

    class Meta:
        db_table = "gen_archivo"
        ordering = ["-id"]