import django_filters
from ruteo.models.novedad_tipo import RutNovedadTipo

class NovedadTipoFilter(django_filters.FilterSet):    
    class Meta:
        model = RutNovedadTipo
        fields = {'id': ['exact'],
                  'nombre': ['icontains']
                  }