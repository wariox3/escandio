import django_filters
from ruteo.models.visita import RutVisita

class NumberInFilter(django_filters.BaseInFilter, django_filters.NumberFilter):
    pass

class VisitaFilter(django_filters.FilterSet):    
    franja_id__in = NumberInFilter(field_name='franja_id', lookup_expr='in')
    class Meta:
        model = RutVisita
        fields = {'id': ['exact'],
                  'despacho_id' : ['exact'],
                  'numero': ['exact'],
                  'documento': ['exact', 'icontains'],
                  'estado_entregado': ['exact'],
                  'estado_novedad': ['exact'],
                  'estado_despacho': ['exact'],
                  'estado_decodificado': ['exact'],
                  'estado_decodificado_alerta': ['exact'],
                  'fecha': ['gte', 'lte', 'gt', 'lt', 'exact'], 
                  'fecha_entrega': ['gte', 'lte', 'gt', 'lt', 'exact'], 
                  'destinatario':['icontains'],
                  'franja_id': ['exact'],
                  }