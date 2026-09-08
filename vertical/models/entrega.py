from django.db import models

class VerEntrega(models.Model):        
    fecha = models.DateTimeField(null=True)
    peso = models.FloatField(default=0)
    volumen = models.FloatField(default=0)
    tiempo_servicio = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    tiempo_trayecto = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    tiempo = models.DecimalField(max_digits=12, decimal_places=6, default=0)    
    visitas = models.FloatField(default=0)    
    visitas_entregadas = models.FloatField(default=0)
    despacho_id = models.IntegerField(default=0)
    # Codigo del despacho en el sistema origen (Semantica): es el que la EMPRESA
    # y el CONDUCTOR reconocen. El Home mostraba `despacho_id` (id interno de BD),
    # que a nadie le dice nada. Se guarda aca (tabla base cross-tenant) porque el
    # Home lista despachos de varios tenants y no puede entrar a cada schema.
    codigo_complemento = models.IntegerField(null=True)
    contenedor_id = models.IntegerField()
    schema_name = models.CharField(max_length=100, null=True)
    usuario_id = models.IntegerField(null=True)

    class Meta:
        db_table = "ver_entrega"
        ordering = ["-id"]