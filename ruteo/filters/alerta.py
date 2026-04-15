import django_filters
from ruteo.models.alerta import RutAlerta


class AlertaFilter(django_filters.FilterSet):
    class Meta:
        model = RutAlerta
        fields = {
            'id': ['exact'],
            'tipo': ['exact'],
            'leida': ['exact'],
            'despacho_id': ['exact'],
            'usuario_id': ['exact'],
        }
