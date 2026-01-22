import django_filters
from general.models.ciudad import GenCiudad

class CiudadFilter(django_filters.FilterSet):    
    class Meta:
        model = GenCiudad        
        fields = {
            'id': ['exact', 'lte'],
            'nombre':['icontains']
        }