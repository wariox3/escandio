import base64
import secrets
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import UpdateModelMixin
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404
from contenedor.models import User, CtnVerificacion
from contenedor.serializers.user import UserSerializer, UserUpdateSerializer, UserSeleccionarSerializador
from contenedor.serializers.verificacion import CtnVerificacionSerializador
from datetime import datetime, timedelta
from utilidades.zinc import Zinc
from decouple import config
from utilidades.space_do import SpaceDo
from PIL import Image
from io import BytesIO
from django.conf import settings

class UsuarioViewSet(GenericViewSet, UpdateModelMixin):
    model = User
    queryset = User.objects.all()
    serializer_class = UserSerializer

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
    
    def get_object(self, pk):
        return get_object_or_404(self.model, pk=pk)

    def list(self, request):        
        queryset = User.objects.all()
        serializer_class = UserSerializer(queryset, many=True)
        return Response(serializer_class.data, status=status.HTTP_200_OK)
    
    def retrieve(self, request, pk=None):
        user = self.get_object(pk)
        user_serializer = self.serializer_class(user)
        return Response(user_serializer.data)

    def update(self, request, pk=None, partial=False):
        user = self.get_object(pk)
        user_serializer = UserUpdateSerializer(user, data=request.data, partial=partial)
        if user_serializer.is_valid():
            user_serializer.save()
            return Response({'actualizacion': True, 'usuario': user_serializer.data}, status=status.HTTP_201_CREATED)            
        return Response({'mensaje':'Errores en la actualizacion del usuario', 'codigo':10, 'validaciones': user_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)  
    
    @action(detail=False, methods=["get"], url_path=r'admin-lista', permission_classes=[permissions.IsAdminUser])
    def admin_lista(self, request):
        from contenedor.models import Contenedor, UsuarioContenedor
        usuarios = User.objects.all().order_by('-fecha_creacion')

        # Contenedores donde es admin (FK)
        admin_de = {}
        for c in Contenedor.objects.exclude(schema_name='public').filter(usuario__isnull=False).values('usuario_id', 'nombre', 'schema_name'):
            admin_de.setdefault(c['usuario_id'], []).append(
                {'nombre': c['nombre'], 'schema_name': c['schema_name']}
            )

        # Contenedores donde fue invitado
        invitado_a = {}
        for uc in UsuarioContenedor.objects.select_related('contenedor').values(
            'usuario_id', 'rol', 'contenedor__nombre', 'contenedor__schema_name'
        ):
            invitado_a.setdefault(uc['usuario_id'], []).append({
                'nombre': uc['contenedor__nombre'],
                'schema_name': uc['contenedor__schema_name'],
                'rol': uc['rol'],
            })

        data = []
        for u in usuarios:
            data.append({
                'id': u.id,
                'username': u.username,
                'nombre': u.nombre,
                'apellido': u.apellido,
                'correo': u.correo,
                'is_active': u.is_active,
                'is_staff': u.is_staff,
                'is_superuser': u.is_superuser,
                'verificado': u.verificado,
                'fecha_creacion': u.fecha_creacion,
                'admin_de': admin_de.get(u.id, []),
                'invitado_a': invitado_a.get(u.id, []),
            })
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path=r'admin-toggle-activo', permission_classes=[permissions.IsAdminUser])
    def admin_toggle_activo(self, request, pk=None):
        user = self.get_object(pk)
        user.is_active = not user.is_active
        user.save()
        return Response(
            {'id': user.id, 'is_active': user.is_active},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path=r'admin-asignar-contenedor', permission_classes=[permissions.IsAdminUser])
    def admin_asignar_contenedor(self, request):
        """Asigna un usuario a un contenedor con rol específico.
        rol='admin' → reemplaza Contenedor.usuario (el anterior pasa a 'usuario').
        rol='usuario' → crea/actualiza UsuarioContenedor con rol='usuario'.
        Identifica el contenedor por schema_name o contenedor_id."""
        from contenedor.models import Contenedor, UsuarioContenedor
        raw = request.data
        usuario_id = raw.get('usuario_id')
        schema_name = raw.get('schema_name')
        contenedor_id = raw.get('contenedor_id')
        rol = (raw.get('rol') or 'usuario').lower()
        if rol not in ('admin', 'usuario'):
            return Response({'mensaje':'rol debe ser admin o usuario', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
        if not usuario_id or (not schema_name and not contenedor_id):
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
        try:
            if schema_name:
                contenedor = Contenedor.objects.get(schema_name=schema_name)
            else:
                contenedor = Contenedor.objects.get(pk=contenedor_id)
        except Contenedor.DoesNotExist:
            return Response({'mensaje':'Contenedor no existe', 'codigo':13}, status=status.HTTP_404_NOT_FOUND)
        try:
            nuevo = User.objects.get(pk=usuario_id)
        except User.DoesNotExist:
            return Response({'mensaje':'Usuario no existe', 'codigo':17}, status=status.HTTP_404_NOT_FOUND)

        if rol == 'admin':
            admin_anterior_id = contenedor.usuario_id
            if admin_anterior_id == nuevo.id:
                return Response({'mensaje':'Ese usuario ya es admin', 'codigo':2}, status=status.HTTP_400_BAD_REQUEST)
            contenedor.usuario = nuevo
            contenedor.save()
            UsuarioContenedor.objects.filter(usuario_id=nuevo.id, contenedor_id=contenedor.id).delete()
            if admin_anterior_id and admin_anterior_id != nuevo.id:
                UsuarioContenedor.objects.get_or_create(
                    usuario_id=admin_anterior_id,
                    contenedor_id=contenedor.id,
                    defaults={'rol': 'usuario'},
                )
            return Response({'mensaje':'Asignado como admin', 'contenedor_id': contenedor.id}, status=status.HTTP_200_OK)
        else:
            if contenedor.usuario_id == nuevo.id:
                return Response({'mensaje':'Ese usuario ya es admin del contenedor', 'codigo':2}, status=status.HTTP_400_BAD_REQUEST)
            uc, creado = UsuarioContenedor.objects.get_or_create(
                usuario_id=nuevo.id,
                contenedor_id=contenedor.id,
                defaults={'rol': 'usuario'},
            )
            if not creado and uc.rol != 'usuario':
                uc.rol = 'usuario'
                uc.save()
            if creado:
                contenedor.usuarios = (contenedor.usuarios or 0) + 1
                contenedor.save()
            return Response({'mensaje':'Asignado como usuario', 'contenedor_id': contenedor.id}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path=r'admin-cambiar-admin-contenedor', permission_classes=[permissions.IsAdminUser])
    def admin_cambiar_admin_contenedor(self, request):
        """Asigna a un usuario como admin (Contenedor.usuario) de un contenedor.
        Identifica el contenedor por schema_name. Quien era admin pasa a 'usuario'."""
        from contenedor.models import Contenedor, UsuarioContenedor
        raw = request.data
        usuario_id = raw.get('usuario_id')
        schema_name = raw.get('schema_name')
        contenedor_id = raw.get('contenedor_id')
        if not usuario_id or (not schema_name and not contenedor_id):
            return Response({'mensaje':'Faltan parametros (usuario_id y schema_name o contenedor_id)', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
        try:
            if schema_name:
                contenedor = Contenedor.objects.get(schema_name=schema_name)
            else:
                contenedor = Contenedor.objects.get(pk=contenedor_id)
        except Contenedor.DoesNotExist:
            return Response({'mensaje':'Contenedor no existe', 'codigo':13}, status=status.HTTP_404_NOT_FOUND)
        try:
            nuevo = User.objects.get(pk=usuario_id)
        except User.DoesNotExist:
            return Response({'mensaje':'Usuario no existe', 'codigo':17}, status=status.HTTP_404_NOT_FOUND)

        admin_anterior_id = contenedor.usuario_id
        contenedor.usuario = nuevo
        contenedor.save()
        # Si el nuevo era invitado, sale de invitados
        UsuarioContenedor.objects.filter(usuario_id=nuevo.id, contenedor_id=contenedor.id).delete()
        # El admin anterior queda como invitado
        if admin_anterior_id and admin_anterior_id != nuevo.id:
            UsuarioContenedor.objects.get_or_create(
                usuario_id=admin_anterior_id,
                contenedor_id=contenedor.id,
                defaults={'rol': 'usuario'},
            )
        return Response(
            {'mensaje': 'Admin cambiado', 'contenedor_id': contenedor.id},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path=r'seleccionar')
    def seleccionar_action(self, request):
        limit = request.query_params.get('limit', 10)
        username = request.query_params.get('username__icontains', None)
        queryset = self.get_queryset()
        if username:
            queryset = queryset.filter(username__icontains=username)
        try:
            limit = int(limit)
            queryset = queryset[:limit]
        except ValueError:
            pass    
        serializer = UserSeleccionarSerializador(queryset, many=True)        
        return Response(serializer.data)       

    @action(detail=False, methods=["post"], url_path=r'nuevo',)
    def nuevo_action(self, request):
        raw = request.data
        username = raw.get('username', None)
        password = raw.get('password', None)
        nombre_corto = raw.get('nombre_corto', None)
        nombre = raw.get('nombre', None)
        apellido = raw.get('apellido', None)
        telefono = raw.get('telefono', None)        
        if username and password:                    
            data = {
                'username': username,
                'password': password,
                'nombre_corto': nombre_corto,
                'nombre': nombre,
                'apellido': apellido,
                'telefono': telefono,
            }
            serializador_usuario = UserSerializer(data=data)
            if serializador_usuario.is_valid():
                usuario = serializador_usuario.save()
                token = secrets.token_urlsafe(20)
                data = {
                    'usuario_id': usuario.id,
                    'token': token,
                    'vence': datetime.now().date() + timedelta(days=1)
                }
                serializador_verificacion = CtnVerificacionSerializador(data = data)
                if serializador_verificacion.is_valid():                                             
                    serializador_verificacion.save()                                                
                    url = f"https://app.ruteo.co/auth/verificacion/" + token                        
                    if config('ENV') == "test":
                        url = f"http://app.ruteo.online/auth/verificacion/" + token
                    if config('ENV') == "dev":
                        url = f"http://localhost:4200/auth/verificacion/" + token
                    
                    html_content = """
                                    <h1>¡Hola {usuario}!</h1>
                                    <p>Estamos comprometidos con la seguridad de tu cuenta, por esta razón necesitamos que nos valides 
                                    que eres tú, por favor verifica tu cuenta haciendo clic en el siguiente enlace.</p>
                                    <a href='{url}' class='button'>Verificar cuenta</a>
                                    """.format(url=url, usuario=usuario.nombre_corto)
                    correo = Zinc()  
                    correo.correo(usuario.correo, f'Verificar cuenta de Ruteo.co', html_content, 'ruteo')  
                    return Response({'usuario': serializador_usuario.data}, status=status.HTTP_201_CREATED)
                return Response({'mensaje':'Errores en el registro de la verificacion', 'codigo':3, 'validaciones': serializador_verificacion.errors}, status=status.HTTP_400_BAD_REQUEST)                                                
            else:
                return Response({'mensaje':'Errores en el registro del usuario', 'codigo':2, 'validaciones': serializador_usuario.errors}, status=status.HTTP_400_BAD_REQUEST)     
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':2}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path=r'cambio-clave-solicitar',)
    def cambio_clave_solicitar(self, request):
        raw = request.data            
        username = raw.get('username')        
        if username:
            try:
                usuario = User.objects.get(username = username)
            except User.DoesNotExist:
                return Response({'mensaje':'El usuario no existe', 'codigo':8}, status=status.HTTP_400_BAD_REQUEST)    
            
            token = secrets.token_urlsafe(20)            
            data = {
                'token': token,
                'vence': datetime.now().date() + timedelta(days=1),
                'usuario_id': usuario.id,
                'accion': 'clave'
            }
            verificacion_serializer = CtnVerificacionSerializador(data = data)
            if verificacion_serializer.is_valid():                                             
                verificacion_serializer.save()
                url = f"https://app.ruteo.co/auth/clave/cambiar/" + token
                if config('ENV') == "test":
                    url = f"http://app.ruteo.online/auth/clave/cambiar/" + token
                if config('ENV') == "dev":
                    url = f"http://localhost:4200/auth/clave/cambiar/" + token  

                html_content = """
                                <h1>¡Hola {usuario}!</h1>
                                <p>Recibimos una solicitud para cambiar tu clave, puedes cambiarla haciendo clic en 
                                el siguiente enlace.</p>
                                <a href='{url}' class='button'>Cambiar clave</a>
                                """.format(url=url, usuario=usuario.nombre_corto)
                correo = Zinc()  
                correo.correo(usuario.correo, f'Solicitud cambio clave Ruteo.co', html_content, 'ruteo')
                return Response({'verificacion': verificacion_serializer.data}, status=status.HTTP_201_CREATED)
            return Response({'mensaje':'Errores en el registro de la verificacion', 'codigo':3, 'validaciones': verificacion_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)            
        return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path=r'cambio-clave-verificar',)
    def cambio_clave_verificar(self, request):
        raw = request.data
        try:
            token = raw.get('token')
            clave = raw.get('password')
            if token and clave:
                verificacion = CtnVerificacion.objects.filter(token=token).first()
                if verificacion:
                    if verificacion.estado_usado == False:
                        fechaActual = datetime.now().date()                
                        if fechaActual <= verificacion.vence:
                            usuario = User.objects.get(pk=verificacion.usuario_id)
                            verificacion.estado_usado = True
                            verificacion.save()
                            usuario.set_password(clave)
                            usuario.save()
                            return Response({'cambio': True}, status=status.HTTP_200_OK)
                        return Response({'mensaje':'El token de la verificacion esta vencido', 'codigo': 6, 'codigoUsuario': verificacion.usuario_id}, status=status.HTTP_400_BAD_REQUEST)
                    return Response({'mensaje':'La verificacion ya fue usada', 'codigo': 5, 'codigoUsuario': verificacion.usuario_id}, status=status.HTTP_400_BAD_REQUEST)
                return Response({'mensaje':'No se ha encontrado la verificacion', 'codigo': 4}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'mensaje':'Faltan parametros', 'codigo': 1}, status=status.HTTP_400_BAD_REQUEST)                
        except User.DoesNotExist:
            return Response({'mensaje':'El usuario no existe', 'codigo':8}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path=r'cambio-clave',)
    def cambio_clave(self, request):
        raw = request.data
        try:
            usuario_id = raw.get('usuario_id')
            clave = raw.get('password')
            if usuario_id and clave:                            
                usuario = User.objects.get(pk=usuario_id)
                usuario.set_password(clave)
                usuario.save()
                return Response({'cambio': True}, status=status.HTTP_200_OK)                
            return Response({'mensaje':'Faltan parametros', 'codigo': 1}, status=status.HTTP_400_BAD_REQUEST)                
        except User.DoesNotExist:
            return Response({'mensaje':'El usuario no existe', 'codigo':8}, status=status.HTTP_400_BAD_REQUEST)             

    @action(detail=False, methods=["post"], url_path=r'cargar-imagen',)
    def cargar_imagen(self, request):
        try:
            raw = request.data
            usuario_id = raw.get('usuario_id')
            imagenB64 = raw.get('imagenB64')
            if usuario_id and imagenB64:
                usuario = User.objects.get(pk=usuario_id)
                arrDatosB64 = imagenB64.split(",")
                base64Crudo = arrDatosB64[1]
                arrTipo = arrDatosB64[0].split(";")
                arrData = arrTipo[0].split(":")
                contentType = arrData[1]

                img_data = base64.b64decode(base64Crudo)
                img = Image.open(BytesIO(img_data))

                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background

                # Crear thumbnail (versión pequeña)
                thumbnail_size = (100, 100)  # Tamaño adecuado para menús
                img.thumbnail(thumbnail_size)

                # Guardamos el original
                archivo = f"escandio/{config('ENV')}/usuario/imagen_{usuario_id}.jpg"
                spaceDo = SpaceDo()
                spaceDo.putB64(archivo, base64Crudo, contentType)

                #Guardar thumbnail
                thumb_io = BytesIO()
                img.save(thumb_io, format='JPEG', quality=85)  
                thumb_data = thumb_io.getvalue()
                archivo_thumb = f"escandio/{config('ENV')}/usuario/imagen_thumb_{usuario_id}.jpg"
                spaceDo.putB64(archivo_thumb, base64.b64encode(thumb_data).decode('utf-8'), contentType)

                usuario.imagen = archivo
                usuario.imagen_thumbnail = archivo_thumb
                usuario.save()
                return Response({'cargar':True, 
                                 'imagen':f"https://{config('DO_BUCKET')}.{config('DO_REGION')}.digitaloceanspaces.com/{archivo}",
                                 'imagen_thumbnail':f"https://{config('DO_BUCKET')}.{config('DO_REGION')}.digitaloceanspaces.com/{archivo_thumb}"}, status=status.HTTP_200_OK)                  
            else: 
                return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({'mensaje':'El usuario no existe', 'codigo':15}, status=status.HTTP_404_NOT_FOUND)  

    @action(detail=False, methods=["post"], url_path=r'limpiar-imagen',)
    def limpiar_imagen(self, request):
        try:
            raw = request.data
            usuario_id = raw.get('usuario_id')    
            if usuario_id:
                usuario = User.objects.get(pk=usuario_id)                
                spaceDo = SpaceDo()
                spaceDo.eliminar(usuario.imagen)
                usuario.imagen = f"escandio/usuario_defecto.jpg"
                usuario.imagen_thumbnail = f"escandio/usuario_defecto.jpg"
                usuario.save()
                return Response({'limpiar':True, 
                                 'imagen':f"https://{config('DO_BUCKET')}.{config('DO_REGION')}.digitaloceanspaces.com/{usuario.imagen}",
                                 'imagen_thumbnail':f"https://{config('DO_BUCKET')}.{config('DO_REGION')}.digitaloceanspaces.com/{usuario.imagen}"}, status=status.HTTP_200_OK)                  
            else: 
                return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({'mensaje':'El usuario no existe', 'codigo':15}, status=status.HTTP_404_NOT_FOUND)  

    @action(detail=False, methods=["get"], url_path=r'saldo/(?P<id>\d+)')
    def saldo(self, request, id=None):        
        usuario = User.objects.get(id=id)
        if usuario:
            return Response({'saldo': usuario.vr_saldo, 'credito': usuario.vr_credito, 'abono': usuario.vr_abono}, status=status.HTTP_200_OK)
        return Response({'mensaje':'El usuario no existe', 'codigo': 4}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=["post"], url_path=r'estado-verificado',)
    def estado_verificado(self, request):
        raw = request.data
        try:
            usuario_id = raw.get('usuario_id')
            if usuario_id:                            
                usuario = User.objects.get(pk=usuario_id)
                return Response({'verificado': usuario.verificado}, status=status.HTTP_200_OK)                
            return Response({'mensaje':'Faltan parametros', 'codigo': 1}, status=status.HTTP_400_BAD_REQUEST)                
        except User.DoesNotExist:
            return Response({'mensaje':'El usuario no existe', 'codigo':8}, status=status.HTTP_400_BAD_REQUEST)   
     
    @action(detail=False, methods=["get"], permission_classes=[permissions.AllowAny], url_path=r'detalle/(?P<id>\d+)')
    def detalle(self, request, id=None):        
        usuario = User.objects.get(id=id)
        if usuario:
            usuarioSerializador = UserSerializer(usuario)
            informacionesFacturaciones = CtnInformacionFacturacion.objects.filter(usuario_id=id)
            informacionesFacturacionesSerializador = CtnInformacionFacturacionSerializador(informacionesFacturaciones, many=True)
            return Response({
                'usuario': usuarioSerializador.data, 
                'informaciones_facturaciones': informacionesFacturacionesSerializador.data}, status=status.HTTP_200_OK)
        return Response({'mensaje':'El usuario no existe', 'codigo': 4}, status=status.HTTP_400_BAD_REQUEST)  

    @action(detail=False, methods=["post"], url_path=r'verificar',)
    def verificar(self, request):
        tokenUrl = request.data.get('token')
        if tokenUrl:
            verificacion = CtnVerificacion.objects.filter(token=tokenUrl).first()
            if verificacion:
                if verificacion.estado_usado == False:
                    fechaActual = datetime.now().date()                
                    if fechaActual <= verificacion.vence:
                        verificacion.estado_usado = True
                        verificacion.save()
                        usuario = User.objects.get(id = verificacion.usuario_id)
                        usuario.verificado = True
                        usuario.save()
                        verificacionSerializer = CtnVerificacionSerializador(verificacion)                
                        return Response({'verificado': True, 'verificacion': verificacionSerializer.data}, status=status.HTTP_200_OK)
                    return Response({'mensaje':'El token de la verificacion esta vencido', 'codigo': 6, 'codigoUsuario': verificacion.usuario_id}, status=status.HTTP_400_BAD_REQUEST)
                return Response({'mensaje':'La verificacion ya fue usada', 'codigo': 5, 'codigoUsuario': verificacion.usuario_id}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'mensaje':'No se ha encontrado la verificacion', 'codigo': 4}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'mensaje':'Faltan parametros', 'codigo': 1}, status=status.HTTP_400_BAD_REQUEST)        

        