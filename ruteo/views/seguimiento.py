from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from ruteo.models.seguimiento import RutSeguimiento
from ruteo.serializers.seguimiento import RutSeguimientoSerializador
from ruteo.filters.seguimiento import SeguimientoFilter
from rest_framework.filters import OrderingFilter
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend



class RutSeguimientoViewSet(viewsets.ModelViewSet):
    queryset = RutSeguimiento.objects.all()
    serializer_class = RutSeguimientoSerializador
    permission_classes = [permissions.IsAuthenticated]    
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = SeguimientoFilter   
    serializadores = {
        'trafico' : RutSeguimientoSerializador
    }

    def get_serializer_class(self):
        serializador_parametro = self.request.query_params.get('serializador', None)
        if not serializador_parametro or serializador_parametro not in self.serializadores:
            return RutSeguimientoSerializador
        return self.serializadores[serializador_parametro]

    def get_queryset(self):
        page_size = self.request.query_params.get('page_size')
        if page_size:
            if page_size != '0':
                self.pagination_class = PageNumberPagination
                self.pagination_class.page_size = int(page_size)
        queryset = super().get_queryset()
        serializer_class = self.get_serializer_class()        
        select_related = getattr(serializer_class.Meta, 'select_related_fields', [])
        if select_related:
            queryset = queryset.select_related(*select_related)        
        campos = serializer_class.Meta.fields        
        if campos and campos != '__all__':
            queryset = queryset.only(*campos) 
        return queryset 

    def list(self, request, *args, **kwargs):
            if request.query_params.get('lista_completa', '').lower() == 'true':
                self.pagination_class = None
            return super().list(request, *args, **kwargs)
    
    