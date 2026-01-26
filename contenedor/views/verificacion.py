from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework import status
from contenedor.serializers.verificacion import CtnVerificacionSerializador
from contenedor.models import CtnVerificacion
from contenedor.models import User
from rest_framework.decorators import action
import secrets
from decouple import config
from datetime import datetime, timedelta
from utilidades.zinc import Zinc

class VerificacionViewSet(viewsets.ModelViewSet):
    queryset = CtnVerificacion.objects.all()
    serializer_class = CtnVerificacionSerializador

    @action(detail=False, methods=["post"], url_path=r'reenviar-verificacion',)
    def reenviar_verificacion(self, request):
        usuario_id = request.data.get('usuario_id')
        if usuario_id:
            try:
                usuario = User.objects.get(pk=usuario_id)
                token = secrets.token_urlsafe(20)                           
                datos = {
                    'usuario_id': usuario.id,
                    'token': token,
                    'vence': datetime.now().date() + timedelta(days=1)
                }
                
                verificacion_serializer = CtnVerificacionSerializador(data = datos)                                           
                if verificacion_serializer.is_valid():
                    verificacion_serializer.save()
                    dominio = config('DOMINIO_FRONTEND')                
                    url = 'https://' + dominio + '/auth/verificacion/' + token
                    html_content = """
                                    <h1>¡Hola {usuario}!</h1>
                                    <p>Estamos comprometidos con la seguridad de tu cuenta, por esta razón necesitamos que nos valides 
                                    que eres tú, por favor verifica tu cuenta haciendo clic en el siguiente enlace.</p>
                                    <a href='{url}' class='button'>Verificar cuenta</a>
                                    """.format(url=url, usuario=usuario.nombre_corto)
                    correo = Zinc()  
                    correo.correo(usuario.correo, 'Verificar cuenta de RedDoc', html_content)  
                    return Response({'verificacion': verificacion_serializer.data}, status=status.HTTP_201_CREATED)
                return Response({'mensaje':'Errores en el registro de la verificacion', 'codigo':3, 'validaciones': verificacion_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
            except User.DoesNotExist:
                return Response({'mensaje': 'El usuario no existe', 'codigo': 1}, status=status.HTTP_400_BAD_REQUEST)             
        else:
            return Response({'mensaje': 'Faltan parámetros', 'codigo': 1}, status=status.HTTP_400_BAD_REQUEST)         
        