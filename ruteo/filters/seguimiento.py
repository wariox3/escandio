import django_filters
from ruteo.models.seguimiento import RutSeguimiento

class SeguimientoFilter(django_filters.FilterSet):    
    
    class Meta:
        model = RutSeguimiento
        fields = {'id': ['exact'], 
                  'despacho_id': ['exact'],}