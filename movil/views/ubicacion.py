"""Vista de tracking de ubicacion de la API movil v2."""
from drf_spectacular.utils import extend_schema
from rest_framework import generics

from movil.permissions import EsConductorMovil
from movil.serializers.ubicacion import UbicacionMovilSerializer
from movil.views.base import MovilApiMixin
from ruteo.servicios.alerta import AlertaServicio


class UbicacionMovilView(MovilApiMixin, generics.CreateAPIView):
    """Recibe los puntos de tracking que la app envia en background."""
    permission_classes = [EsConductorMovil]
    serializer_class = UbicacionMovilSerializer

    @extend_schema(tags=['ubicacion'])
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def perform_create(self, serializer):
        ubicacion = serializer.save(usuario_id=self.request.user.id)
        if ubicacion.despacho:
            despacho = ubicacion.despacho
            despacho.fecha_ubicacion = ubicacion.fecha
            despacho.latitud = ubicacion.latitud
            despacho.longitud = ubicacion.longitud
            despacho.save(update_fields=['fecha_ubicacion', 'latitud', 'longitud'])
            AlertaServicio.evaluar(ubicacion)
