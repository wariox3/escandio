import django_filters
from general.models.complemento import GenComplemento

class ComplementoFilter(django_filters.FilterSet):    
    class Meta:
        model = GenComplemento        
        fields = {
            'id': ['exact', 'lte'],
            'instalado': ['exact']
        }