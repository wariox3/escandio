from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from ruteo.models.alerta import RutAlerta
from ruteo.serializers.alerta import RutAlertaSerializador
from ruteo.filters.alerta import AlertaFilter


class RutAlertaViewSet(viewsets.ModelViewSet):
    queryset = RutAlerta.objects.all()
    serializer_class = RutAlertaSerializador
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = AlertaFilter
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        queryset = super().get_queryset()
        select_related = getattr(self.serializer_class.Meta, 'select_related_fields', [])
        if select_related:
            queryset = queryset.select_related(*select_related)
        return queryset

    @action(detail=False, methods=['post'], url_path=r'marcar_leidas')
    def marcar_leidas(self, request):
        ids = request.data.get('ids') or []
        qs = RutAlerta.objects.filter(leida=False)
        if ids:
            qs = qs.filter(id__in=ids)
        actualizadas = qs.update(leida=True, fecha_leida=timezone.now())
        return Response({'mensaje': f'{actualizadas} alertas marcadas como leidas'}, status=status.HTTP_200_OK)
