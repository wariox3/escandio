import django_filters
from ruteo.models.vehiculo import RutVehiculo

class VehiculoFilter(django_filters.FilterSet):    
    class Meta:
        model = RutVehiculo
        fields = {'id': ['exact'],
                  'placa' : ['exact', 'icontains'],
                  'estado_activo': ['exact']
                }