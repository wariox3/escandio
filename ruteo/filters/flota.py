import django_filters
from ruteo.models.flota import RutFlota

class FlotaFilter(django_filters.FilterSet):    
    class Meta:
        model = RutFlota
        fields = {'id': ['exact']
                }