import django_filters
from ruteo.models.novedad import RutNovedad

class NovedadFilter(django_filters.FilterSet):   
    visita__numero = django_filters.NumberFilter(field_name='visita__numero', lookup_expr='exact') 
    class Meta:
        model = RutNovedad
        fields = {'id': ['exact'],
                  'estado_solucion': ['exact'], 
                  'nuevo_complemento': ['exact'],
                  'visita_id': ['exact'],
                  'visita__numero': ['exact'],
                  }