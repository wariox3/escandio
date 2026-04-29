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
        if usuarioEmpresa.rol in ('invitado', 'usuario'):
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
        contenedores_ids = raw.get('contenedores_ids', None)

        if not (usuario_id and usuario_invitado_id):
            return Response({'mensaje':'Faltan parametros', 'codigo':2}, status=status.HTTP_400_BAD_REQUEST)

        # Normalizar a lista de contenedores
        if contenedores_ids and isinstance(contenedores_ids, list):
            ids = [int(x) for x in contenedores_ids if x]
        elif contenedor_id:
            ids = [int(contenedor_id)]
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':2}, status=status.HTTP_400_BAD_REQUEST)

        # Validar que el invitador es admin de cada contenedor (super admin se salta)
        contenedores = Contenedor.objects.filter(id__in=ids)
        if not request.user.is_superuser:
            no_autorizados = [c.id for c in contenedores if c.usuario_id != usuario_id]
            if no_autorizados:
                return Response(
                    {'mensaje': f'No eres administrador de los contenedores {no_autorizados}', 'codigo': 13},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Perfiles y accesos opcionales
        perfil_web = raw.get('perfil_web') or 'operativo'
        perfil_movil = raw.get('perfil_movil')
        tiene_acceso_web = bool(raw.get('tiene_acceso_web', True))
        tiene_acceso_movil = bool(raw.get('tiene_acceso_movil', False))

        creados = []
        ya_existian = []
        for c in contenedores:
            if UsuarioContenedor.objects.filter(usuario_id=usuario_invitado_id, contenedor_id=c.id).exists():
                ya_existian.append(c.id)
                continue
            uc = UsuarioContenedor.objects.create(
                usuario_id=usuario_invitado_id,
                contenedor_id=c.id,
                rol='usuario',
                tiene_acceso_web=tiene_acceso_web,
                tiene_acceso_movil=tiene_acceso_movil,
                perfil_web=perfil_web if tiene_acceso_web else None,
                perfil_movil=perfil_movil if tiene_acceso_movil else None,
            )
            c.usuarios = (c.usuarios or 0) + 1
            c.save()
            creados.append(uc.id)

        return Response(
            {
                'creados': creados,
                'ya_existian': ya_existian,
                'mensaje': 'Asignación procesada',
            },
            status=status.HTTP_201_CREATED if creados else status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path=r'ceder-admin',)
    def ceder_admin(self, request):
        """Transfiere la propiedad del contenedor a otro miembro existente."""
        raw = request.data
        contenedor_id = raw.get('contenedor_id')
        nuevo_admin_id = raw.get('nuevo_admin_id')
        if not (contenedor_id and nuevo_admin_id):
            return Response({'mensaje':'Faltan parametros', 'codigo':2}, status=status.HTTP_400_BAD_REQUEST)

        try:
            contenedor = Contenedor.objects.get(pk=contenedor_id)
        except Contenedor.DoesNotExist:
            return Response({'mensaje':'Contenedor no existe', 'codigo':13}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_superuser and contenedor.usuario_id != request.user.id:
            return Response({'mensaje':'Solo el admin actual puede ceder', 'codigo':13}, status=status.HTTP_403_FORBIDDEN)

        try:
            nuevo = User.objects.get(pk=nuevo_admin_id)
        except User.DoesNotExist:
            return Response({'mensaje':'Usuario no existe', 'codigo':17}, status=status.HTTP_404_NOT_FOUND)

        admin_anterior_id = contenedor.usuario_id
        contenedor.usuario = nuevo
        contenedor.save()

        # El nuevo admin deja de ser usuario invitado (si lo era)
        UsuarioContenedor.objects.filter(usuario_id=nuevo.id, contenedor_id=contenedor.id).delete()

        # El admin anterior queda como usuario invitado
        if admin_anterior_id and admin_anterior_id != nuevo.id:
            UsuarioContenedor.objects.get_or_create(
                usuario_id=admin_anterior_id,
                contenedor_id=contenedor.id,
                defaults={'rol': 'usuario'},
            )

        return Response({'mensaje': 'Administración transferida'}, status=status.HTTP_200_OK)