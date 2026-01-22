import django_filters
from contenedor.models import UsuarioContenedor

class UsuarioContenedorFilter(django_filters.FilterSet):   
    contenedor__nombre = django_filters.CharFilter(field_name='contenedor__nombre', lookup_expr='icontains')  
    class Meta:
        model = UsuarioContenedor
        fields = {
            'id': ['exact', 'lte'],
            'contenedor_id': ['exact'],
            'usuario_id': ['exact'],
            'rol': ['exact'],
            'contenedor__nombre': ['icontains'],    
        }