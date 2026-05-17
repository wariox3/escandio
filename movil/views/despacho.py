"""Vista de despacho/entrega de la API movil v2."""
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from movil.serializers.despacho import DespachoMovilSerializer
from movil.views.base import MovilApiMixin
from vertical.models.entrega import VerEntrega


class DespachoMovilView(MovilApiMixin, generics.RetrieveAPIView):
    """Resuelve un codigo de despacho a su resumen + tenant (schema_name).

    Es el endpoint de arranque: corre en el dominio base (no en un subdominio
    de tenant) porque la app todavia no sabe a que tenant pertenece el codigo.
    Por eso basta IsAuthenticated, no EsConductorMovil.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = DespachoMovilSerializer
    queryset = VerEntrega.objects.all()

    @extend_schema(tags=['despachos'])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
