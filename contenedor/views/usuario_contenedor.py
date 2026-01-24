import secrets
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from contenedor.models import User
from contenedor.models import Contenedor, UsuarioContenedor
from contenedor.serializers.contenedor import ContenedorSerializador
from contenedor.serializers.user import UserSerializer
from contenedor.serializers.usuario_contenedor import UsuarioContenedorSerializador, UsuarioContenedorListaSerializador, UsuarioContenedorConfiguracionSerializador
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from contenedor.filters.usuario_contenedor import UsuarioContenedorFilter
from datetime import datetime, timedelta
from decouple import config
from utilidades.zinc import Zinc
from django.conf import settings
from rest_framework.pagination import PageNumberPagination

class UsuarioContenedorViewSet(viewsets.ModelViewSet):
    queryset = UsuarioContenedor.objects.all()
    serializer_class = UsuarioContenedorSerializador    
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = UsuarioContenedorFilter 
    serializadores = {
        'lista': UsuarioContenedorListaSerializador,
        'configuracion': UsuarioContenedorConfiguracionSerializador
    }

    def get_serializer_class(self):
        serializador_parametro = self.request.query_params.get('serializador', None)
        if not serializador_parametro or serializador_parametro not in self.serializadores:
            return UsuarioContenedorSerializador
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
        if request.query_params.get('excel'):
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
        return super().list(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        usuarioEmpresa = self.get_object()
        if usuarioEmpresa.rol == 'invitado':
            self.perform_destroy(usuarioEmpresa)
            empresa = Contenedor.objects.get(pk=usuarioEmpresa.contenedor_id)
            empresa.usuarios -= 1
            empresa.save()
            return Response(status=status.HTTP_200_OK)
        else:
            return Response({'mensaje':"El usuario propietario no se puede eliminar", 'codigo': 22}, status=status.HTTP_400_BAD_REQUEST)      
        

    @action(detail=False, methods=["post"], url_path=r'nuevo',)
    def nuevo_action(self, request):
        raw = request.data
        usuario_id = raw.get('usuario_id', None)
        usuario_invitado_id = raw.get('usuario_invitado_id', None)
        contenedor_id = raw.get('contenedor_id', None)
        if usuario_id and usuario_invitado_id and contenedor_id:                    
            usuario_contenedor_existente = UsuarioContenedor.objects.filter(usuario_id=usuario_invitado_id, contenedor_id=contenedor_id).first()
            if usuario_contenedor_existente:
                return Response({'mensaje':'El usuario ya pertenece al contenedor', 'codigo':2}, status=status.HTTP_400_BAD_REQUEST)                        
            data = {
                'usuario': usuario_invitado_id,
                'contenedor': contenedor_id,
                'rol': 'invitado'
            }
            serializador = UsuarioContenedorSerializador(data=data)
            if serializador.is_valid():
                usuario_contenedor = serializador.save()                
                return Response({'usuario_contenedor': serializador.data}, status=status.HTTP_201_CREATED)                    
            else:
                return Response({'mensaje':'Errores en el registro del usuario contenedor', 'codigo':2, 'validaciones': serializador.errors}, status=status.HTTP_400_BAD_REQUEST)     
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':2}, status=status.HTTP_400_BAD_REQUEST)                        