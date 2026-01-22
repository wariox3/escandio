import django_filters
from ruteo.models.ubicacion import RutUbicacion

class UbicacionFilter(django_filters.FilterSet):    
    class Meta:
        model = RutUbicacion
        fields = {'id': ['exact'],
                  'despacho_id' : ['exact'],
                  'visita_id' : ['exact'],
                  }