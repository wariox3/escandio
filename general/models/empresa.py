from django.db import models
from general.models.ciudad import GenCiudad

class GenEmpresa(models.Model):   
    id = models.BigIntegerField(primary_key=True)     
    numero_identificacion = models.CharField(max_length=20, null=True)
    digito_verificacion = models.CharField(max_length=1, null=True)
    nombre_corto = models.CharField(max_length=200)
    direccion = models.CharField(max_length=50, null=True)
    telefono = models.CharField(max_length=50, null=True)
    correo = models.EmailField(max_length = 255)
    imagen = models.TextField(null=True)
    contenedor_id = models.IntegerField()        
    subdominio = models.CharField(max_length=100, default='demo') 
    ciudad = models.ForeignKey(GenCiudad, null=True, on_delete=models.PROTECT)

    class Meta:
        db_table = "gen_empresa"
        ordering = ["-id"]