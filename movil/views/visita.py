"""Vistas de visitas de la API movil v2."""
from datetime import datetime

from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from movil import responses
from movil.permissions import EsConductorMovil
from movil.serializers.comunes import MensajeSerializer
from movil.serializers.visita import EntregaRequestSerializer, VisitaMovilSerializer
from movil.services.entrega import registrar_entrega
from movil.services.errores import EvidenciaNoGuardada
from movil.views.base import MovilApiMixin
from ruteo.filters.visita import VisitaFilter
from ruteo.models.visita import RutVisita


class VisitaMovilViewSet(MovilApiMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Visitas del conductor. Sin paginar: la app descarga la ruta completa.

    Filtros utiles: ?despacho_id=&estado_entregado=&estado_novedad=
    """
    permission_classes = [EsConductorMovil]
    serializer_class = VisitaMovilSerializer
    queryset = RutVisita.objects.select_related('ciudad', 'despacho').all()
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = VisitaFilter
    ordering_fields = ['orden', 'fecha', 'numero']
    ordering = ['orden']
    pagination_class = None

    @extend_schema(tags=['visitas'])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=EntregaRequestSerializer,
        responses={200: MensajeSerializer},
        tags=['visitas'],
    )
    @action(detail=True, methods=['post'], url_path='entregar')
    def entregar(self, request, pk=None):
        # pk no numerico en la URL (router regex [^/.]+) -> ValueError en el ORM.
        try:
            pk = int(pk)
        except (TypeError, ValueError):
            return responses.error(
                'La visita no existe', responses.COD_NO_ENCONTRADO, 404,
                titulo='No encontrada',
            )
        visita = self.get_queryset().filter(pk=pk).first()
        if visita is None:
            return responses.error(
                'La visita no existe', responses.COD_NO_ENCONTRADO, 404,
                titulo='No encontrada',
            )
        fecha_texto = request.data.get('fecha_entrega')
        if not fecha_texto:
            return responses.error(
                'Falta la fecha de entrega', responses.COD_PARAMETROS, 400,
                titulo='Datos invalidos',
            )
        try:
            fecha_entrega = timezone.make_aware(
                datetime.strptime(fecha_texto, '%Y-%m-%d %H:%M'),
            )
        except (ValueError, TypeError):
            return responses.error(
                'Formato de fecha invalido. Use YYYY-MM-DD HH:MM',
                responses.COD_PARAMETROS, 400, titulo='Datos invalidos',
            )
        if fecha_entrega > timezone.now():
            return responses.error(
                'La fecha de entrega no puede ser futura',
                responses.COD_PARAMETROS, 400, titulo='Datos invalidos',
            )
        if visita.estado_entregado:
            return Response({'mensaje': 'La visita ya estaba entregada'})

        try:
            registrar_entrega(
                visita=visita,
                fecha_entrega=fecha_entrega,
                imagenes=request.FILES.getlist('imagenes'),
                firmas=request.FILES.getlist('firmas'),
                datos_adicionales=request.data.get('datos_adicionales'),
                tenant=request.tenant,
            )
        except EvidenciaNoGuardada:
            return responses.error(
                'No se pudieron subir las fotos/firmas (almacenamiento no '
                'disponible). La entrega no se registró; reintenta en un momento.',
                responses.COD_SERVIDOR, 503, titulo='Reintenta',
            )
        return Response({'mensaje': 'Entrega registrada'})
