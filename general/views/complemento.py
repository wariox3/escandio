from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from general.models.complemento import GenComplemento
from general.serializers.complemento import GenComplementoSerializador
from general.filters.complemento import ComplementoFilter
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from utilidades.holmio import Holmio

class ComplementoViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    queryset = GenComplemento.objects.all()
    serializer_class = GenComplementoSerializador    
    filter_backends = [DjangoFilterBackend, OrderingFilter]    
    filterset_class = ComplementoFilter 
    serializadores = {
        'lista': GenComplementoSerializador
    }

    def get_serializer_class(self):
        serializador_parametro = self.request.query_params.get('serializador', None)
        if not serializador_parametro or serializador_parametro not in self.serializadores:
            return GenComplementoSerializador
        return self.serializadores[serializador_parametro]

    def get_queryset(self):
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
        if request.query_params.get('lista', '').lower() == 'true':
            self.pagination_class = None
        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path=r'validar',)
    def validar_action(self, request):             
        raw = request.data
        id = raw.get('id')            
        if id:
            complemento = GenComplemento.objects.get(pk=id)
            validado = False   
            if id == 1:
                holmio = Holmio()
                respuesta = holmio.estado()
                if respuesta['error'] == False:
                    validado = True
            if validado:
                return Response({'validado' : True,'mensaje': 'complemento validado'}, status=status.HTTP_200_OK)
            else:
                return Response({'validado' : False, 'mensaje':f'Fallo la validacion', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)                                                              
        else:
            return Response({'validado': False, 'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)     