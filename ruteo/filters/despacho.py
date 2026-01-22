import django_filters
from ruteo.models.despacho import RutDespacho

class DespachoFilter(django_filters.FilterSet):    
    vehiculo__placa = django_filters.CharFilter(field_name='vehiculo__placa', lookup_expr='icontains')
    class Meta:
        model = RutDespacho
        fields = {'id': ['exact'],
                  'entrega_id': ['exact'],
                  'fecha': ['gte', 'lte', 'gt', 'lt', 'exact'], 
                  'vehiculo__placa': ['exact', 'icontains'],
                  'estado_aprobado': ['exact'], 
                  'estado_anulado': ['exact'],
                  'estado_terminado': ['exact'], }