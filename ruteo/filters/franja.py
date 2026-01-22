import django_filters
from ruteo.models.franja import RutFranja

class FranjaFilter(django_filters.FilterSet):    
    class Meta:
        model = RutFranja
        fields = {'id': ['exact']
                }