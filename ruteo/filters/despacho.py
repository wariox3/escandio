import django_filters
from django.db.models import Q
from ruteo.models.despacho import RutDespacho

class DespachoFilter(django_filters.FilterSet):
    vehiculo__placa = django_filters.CharFilter(field_name='vehiculo__placa', lookup_expr='icontains')
    # Buscador rapido de Trafico: un solo campo de texto que matchea OE /
    # complemento / id (si es numero) o placa (icontains). Evita el baile de
    # campo+operador+valor del filtro estructurado.
    buscar = django_filters.CharFilter(method='filtrar_buscar', label='Busqueda rapida')

    def filtrar_buscar(self, queryset, name, value):
        v = (value or '').strip()
        if not v:
            return queryset
        q = Q(vehiculo__placa__icontains=v)
        if v.isdigit():
            n = int(v)
            q |= Q(entrega_id=n) | Q(codigo_complemento=n) | Q(id=n)
        return queryset.filter(q)

    class Meta:
        model = RutDespacho
        fields = {'id': ['exact'],
                  'entrega_id': ['exact'],
                  'fecha': ['gte', 'lte', 'gt', 'lt', 'exact'],
                  'vehiculo__placa': ['exact', 'icontains'],
                  # 'isnull' habilita el filtro "Sin asignar" de Trafico:
                  # ?conductor_id__isnull=true -> sin asignar; =false -> asignadas.
                  'conductor_id': ['exact', 'isnull'],
                  'estado_aprobado': ['exact'],
                  'estado_anulado': ['exact'],
                  'estado_terminado': ['exact'], }