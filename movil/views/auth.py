"""Vistas de autenticacion de la API movil v2."""
from django.contrib.auth import authenticate
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from movil import responses
from movil.serializers.auth import (
    LoginSerializer,
    RegistroSerializer,
    SesionSerializer,
    SolicitarClaveSerializer,
    UsuarioMovilSerializer,
)
from movil.serializers.comunes import MensajeSerializer
from movil.services import auth as auth_service
from movil.views.base import MovilApiMixin


class LoginView(MovilApiMixin, APIView):
    """Autentica al conductor y devuelve tokens estandar + usuario."""
    permission_classes = [AllowAny]

    @extend_schema(request=LoginSerializer, responses={200: SesionSerializer}, tags=['auth'])
    def post(self, request):
        entrada = LoginSerializer(data=request.data)
        if not entrada.is_valid():
            return responses.error(
                'Usuario y clave son obligatorios', responses.COD_PARAMETROS, 400,
                titulo='Datos invalidos', extra={'validaciones': entrada.errors},
            )
        usuario = authenticate(
            username=entrada.validated_data['username'].strip(),
            password=entrada.validated_data['password'],
        )
        if usuario is None:
            return responses.error(
                'Usuario o clave incorrectos', responses.COD_CREDENCIALES, 400,
                titulo='Credenciales invalidas',
            )
        if not usuario.is_active:
            return responses.error(
                'Tu cuenta esta inactiva', responses.COD_SIN_PERMISO, 403,
                titulo='Cuenta inactiva',
            )
        if usuario.estado_registro == 'rechazado':
            return responses.error(
                'Tu registro fue rechazado. Comunicate con tu empresa.',
                responses.COD_SIN_PERMISO, 403, titulo='Registro rechazado',
            )
        # Un usuario 'pendiente' SI puede loguear: la app lee usuario.estado
        # y le muestra la pantalla de "pendiente de aprobacion".
        refresh = RefreshToken.for_user(usuario)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'usuario': UsuarioMovilSerializer(usuario).data,
        })


class RegistroView(MovilApiMixin, APIView):
    """Crea una cuenta de conductor y envia el correo de verificacion."""
    permission_classes = [AllowAny]

    @extend_schema(request=RegistroSerializer, responses={201: UsuarioMovilSerializer}, tags=['auth'])
    def post(self, request):
        entrada = RegistroSerializer(data=request.data)
        if not entrada.is_valid():
            return responses.error(
                'Revisa los datos de registro', responses.COD_PARAMETROS, 400,
                titulo='Datos invalidos', extra={'validaciones': entrada.errors},
            )
        usuario, errores = auth_service.crear_usuario(
            entrada.validated_data['username'].strip().lower(),
            entrada.validated_data['password'],
            nombre=entrada.validated_data.get('nombre') or None,
            telefono=entrada.validated_data.get('telefono') or None,
            empresa_nombre=entrada.validated_data.get('empresa_nombre') or None,
        )
        if errores is not None:
            return responses.error(
                'No se pudo crear la cuenta', responses.COD_PARAMETROS, 400,
                titulo='Registro fallido', extra={'validaciones': errores},
            )
        return Response(UsuarioMovilSerializer(usuario).data, status=201)


class SolicitarClaveView(MovilApiMixin, APIView):
    """Solicita el correo de cambio de clave."""
    permission_classes = [AllowAny]

    @extend_schema(request=SolicitarClaveSerializer, responses={200: MensajeSerializer}, tags=['auth'])
    def post(self, request):
        entrada = SolicitarClaveSerializer(data=request.data)
        if not entrada.is_valid():
            return responses.error(
                'El correo es obligatorio', responses.COD_PARAMETROS, 400,
                titulo='Datos invalidos',
            )
        ok, _ = auth_service.solicitar_cambio_clave(
            entrada.validated_data['username'].strip().lower(),
        )
        if not ok:
            return responses.error(
                'No existe una cuenta con ese correo', responses.COD_NO_ENCONTRADO, 404,
                titulo='Cuenta no encontrada',
            )
        return Response({'mensaje': 'Te enviamos un correo para cambiar tu clave'})


class LogoutView(MovilApiMixin, APIView):
    """Cierra la sesion. La invalidacion del token es del lado del cliente:
    la app descarta access y refresh. Endpoint explicito para cerrar el flujo."""
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: MensajeSerializer}, tags=['auth'])
    def post(self, request):
        return Response({'mensaje': 'Sesion cerrada'})


class MeView(MovilApiMixin, APIView):
    """Devuelve el usuario autenticado (estado, acceso_movil, etc.).

    La app lo consulta para re-chequear si su registro ya fue aprobado, sin
    tener que cerrar sesion y volver a entrar (pull-to-refresh).
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: UsuarioMovilSerializer}, tags=['auth'])
    def get(self, request):
        return Response(UsuarioMovilSerializer(request.user).data)


class TokenRefreshMovilView(MovilApiMixin, TokenRefreshView):
    """Renueva el access token a partir del refresh token."""

    @extend_schema(tags=['auth'])
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
