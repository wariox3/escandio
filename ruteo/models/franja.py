from django.db import models

class RutFranja(models.Model):
    codigo = models.CharField(max_length=20, null=True)
    nombre = models.CharField(max_length=255)
    color = models.CharField(max_length=8, null=True)
    coordenadas = models.JSONField(null=True)
    
    '''coordenadas = [
        {'lat': 0, 'lng': 0},
        {'lat': 1, 'lng': 1},
        {'lat': 1, 'lng': 0},
        {'lat': 0, 'lng': 0}
    ]'''

    class Meta:
        db_table = "rut_franja"
        ordering = ['nombre']