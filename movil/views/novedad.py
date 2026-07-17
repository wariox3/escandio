"""Vistas de novedades de la API movil v2."""
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from movil import responses
from movil.permissions import EsConductorMovil
from movil.serializers.comunes import IdSerializer, MensajeSerializer
from movil.serializers.novedad import (
    CrearNovedadRequestSerializer,
    NovedadTipoMovilSerializer,
    SolucionarNovedadSerializer,
)
from movil.services.errores import EvidenciaNoGuardada
from movil.services.novedad import registrar_novedad
from movil.views.base import MovilApiMixin
from ruteo.models.novedad import RutNovedad
from ruteo.models.novedad_tipo import RutNovedadTipo
from ruteo.models.visita import RutVisita


class NovedadMovilViewSet(MovilApiMixin, viewsets.GenericViewSet):
    """Novedades reportadas por el conductor."""
    permission_classes = [EsConductorMovil]
    serializer_class = NovedadTipoMovilSerializer
    queryset = RutNovedad.objects.all()

    @extend_schema(responses={200: NovedadTipoMovilSerializer(many=True)}, tags=['novedades'])
    @action(detail=False, methods=['get'], url_path='tipos')
    def tipos(self, request):
        tipos = RutNovedadTipo.objects.all().order_by('nombre')
        return Response(NovedadTipoMovilSerializer(tipos, many=True).data)

    @extend_schema(request=CrearNovedadRequestSerializer, responses={201: IdSerializer}, tags=['novedades'])
    def create(self, request, *args, **kwargs):
        visita_id = request.data.get('visita_id')
        novedad_tipo_id = request.data.get('novedad_tipo_id')
        fecha_texto = request.data.get('fecha')
        movil_token = request.data.get('movil_token')
        if not (visita_id and novedad_tipo_id and fecha_texto and movil_token):
            return responses.error(
                'Faltan parametros (visita_id, novedad_tipo_id, fecha, movil_token)',
                responses.COD_PARAMETROS, 400, titulo='Datos invalidos',
            )
        # El movil (FormData de React Native) puede mandar "undefined", un UUID o
        # "12.0"; sin esta coercion, filter(pk=...) revienta con ValueError -> 500
        # -> "servidor fuera de linea" + bucle de re-sync. El guard de arriba solo
        # verifica que existan, no que sean numericos.
        try:
            visita_id = int(visita_id)
            novedad_tipo_id = int(novedad_tipo_id)
        except (TypeError, ValueError):
            return responses.error(
                'visita_id y novedad_tipo_id deben ser numericos',
                responses.COD_PARAMETROS, 400, titulo='Datos invalidos',
            )
        visita = RutVisita.objects.filter(pk=visita_id).first()
        if visita is None:
            return responses.error(
                'La visita no existe', responses.COD_NO_ENCONTRADO, 404,
                titulo='No encontrada',
            )
        if not RutNovedadTipo.objects.filter(pk=novedad_tipo_id).exists():
            return responses.error(
                'El tipo de novedad no existe', responses.COD_NO_ENCONTRADO, 404,
                titulo='No encontrado',
            )
        try:
            fecha = timezone.make_aware(datetime.strptime(fecha_texto, '%Y-%m-%d %H:%M'))
        except (ValueError, TypeError):
            return responses.error(
                'Formato de fecha invalido. Use YYYY-MM-DD HH:MM',
                responses.COD_PARAMETROS, 400, titulo='Datos invalidos',
            )
        try:
            novedad = registrar_novedad(
                visita=visita,
                novedad_tipo_id=novedad_tipo_id,
                fecha=fecha,
                descripcion=request.data.get('descripcion'),
                movil_token=movil_token,
                imagenes=request.FILES.getlist('imagenes'),
                tenant=request.tenant,
            )
        except EvidenciaNoGuardada:
            return responses.error(
                'No se pudieron subir las imágenes (almacenamiento no '
                'disponible). La novedad no se registró; reintenta en un momento.',
                responses.COD_SERVIDOR, 503, titulo='Reintenta',
            )
        return Response({'id': novedad.id}, status=201)

    @extend_schema(request=SolucionarNovedadSerializer, responses={200: MensajeSerializer}, tags=['novedades'])
    @action(detail=True, methods=['post'], url_path='solucionar')
    def solucionar(self, request, pk=None):
        # pk no numerico en la URL (router regex [^/.]+) -> ValueError en el ORM.
        try:
            pk = int(pk)
        except (TypeError, ValueError):
            return responses.error(
                'La novedad no existe', responses.COD_NO_ENCONTRADO, 404,
                titulo='No encontrada',
            )
        novedad = RutNovedad.objects.filter(pk=pk).first()
        if novedad is None:
            return responses.error(
                'La novedad no existe', responses.COD_NO_ENCONTRADO, 404,
                titulo='No encontrada',
            )
        if novedad.estado_solucion:
            return responses.error(
                'La novedad ya esta solucionada', responses.COD_CONFLICTO, 409,
                titulo='Ya solucionada',
            )
        with transaction.atomic():
            novedad.estado_solucion = True
            novedad.fecha_solucion = timezone.now()
            novedad.solucion = request.data.get('solucion')
            novedad.save()
            visita = RutVisita.objects.filter(pk=novedad.visita_id).first()
            if visita:
                visita.estado_novedad = False
                visita.save(update_fields=['estado_novedad'])
                if visita.despacho:
                    despacho = visita.despacho
                    despacho.visitas_novedad = (despacho.visitas_novedad or 0) - 1
                    despacho.save(update_fields=['visitas_novedad'])
        return Response({'mensaje': 'Novedad solucionada'})
