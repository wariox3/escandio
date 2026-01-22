from django.db import models
from ruteo.models.despacho import RutDespacho

class RutSeguimiento(models.Model):
    fecha_registro = models.DateTimeField(auto_now_add=True)
    usuario_id = models.IntegerField(null=True) 
    comentario = models.CharField(max_length=500, null=True)
    despacho = models.ForeignKey(RutDespacho, null=True, on_delete=models.PROTECT, related_name='seguimientos_despacho_rel')    

    class Meta:
        db_table = "rut_seguimiento"