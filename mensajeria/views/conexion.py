import secrets
import logging
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import connection
from contenedor.models import Contenedor, CtnWhatsappConexion
from mensajeria.serializers.conexion import CtnWhatsappConexionSerializador
from mensajeria.servicios.cifrado import CifradoServicio
from mensajeria.servicios.whatsapp_cliente import WhatsappCliente

logger = logging.getLogger(__name__)


class CtnWhatsappConexionViewSet(viewsets.ModelViewSet):
    """
    GET /mensajeria/conexion/       -> detalle (retorna el único del tenant actual o 404)
    POST/PUT /mensajeria/conexion/  -> upsert de credenciales del tenant actual
    Siempre opera contra el Contenedor del schema actual (connection.schema_name).
    """
    serializer_class = CtnWhatsappConexionSerializador
    permission_classes = [permissions.IsAuthenticated]

    def _contenedor_actual(self):
        schema = connection.schema_name
        return Contenedor.objects.filter(schema_name=schema).first()

    def get_queryset(self):
        contenedor = self._contenedor_actual()
        if not contenedor:
            return CtnWhatsappConexion.objects.none()
        return CtnWhatsappConexion.objects.filter(contenedor=contenedor)

    def list(self, request, *args, **kwargs):
        conexion = self.get_queryset().first()
        if not conexion:
            return Response({'detail': 'No hay conexión configurada'}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(conexion).data)

    def create(self, request, *args, **kwargs):
        contenedor = self._contenedor_actual()
        if not contenedor:
            return Response({'detail': 'No se pudo identificar el contenedor'}, status=status.HTTP_400_BAD_REQUEST)

        datos = request.data
        access_token = datos.get('access_token', '').strip()
        if not access_token:
            return Response({'access_token': ['Requerido']}, status=status.HTTP_400_BAD_REQUEST)

        phone_number_id = (datos.get('phone_number_id') or '').strip()
        waba_id = (datos.get('waba_id') or '').strip()
        if not phone_number_id or not waba_id:
            return Response({'detail': 'phone_number_id y waba_id son requeridos'}, status=status.HTTP_400_BAD_REQUEST)

        conexion, _ = CtnWhatsappConexion.objects.update_or_create(
            contenedor=contenedor,
            defaults={
                'phone_number_id': phone_number_id,
                'waba_id': waba_id,
                'access_token_cifrado': CifradoServicio.cifrar(access_token),
                'app_secret_cifrado': CifradoServicio.cifrar(datos.get('app_secret')) if datos.get('app_secret') else None,
                'verify_token': datos.get('verify_token') or secrets.token_urlsafe(24),
                'estado': CtnWhatsappConexion.ESTADO_PENDIENTE,
                'error_mensaje': None,
            }
        )

        # Validar credenciales consultando el número
        cliente = WhatsappCliente(conexion)
        resultado = cliente.consultar_numero()
        if resultado['error']:
            conexion.estado = CtnWhatsappConexion.ESTADO_ERROR
            conexion.error_mensaje = resultado.get('mensaje')
            conexion.save()
        else:
            data = resultado.get('data') or {}
            conexion.display_phone_number = data.get('display_phone_number')
            conexion.verified_name = data.get('verified_name')
            conexion.estado = CtnWhatsappConexion.ESTADO_ACTIVO
            conexion.error_mensaje = None
            conexion.save()

        return Response(self.get_serializer(conexion).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def probar(self, request):
        """Reconsulta Meta para validar credenciales."""
        conexion = self.get_queryset().first()
        if not conexion:
            return Response({'detail': 'Sin conexión'}, status=status.HTTP_404_NOT_FOUND)
        cliente = WhatsappCliente(conexion)
        resultado = cliente.consultar_numero()
        if resultado['error']:
            conexion.estado = CtnWhatsappConexion.ESTADO_ERROR
            conexion.error_mensaje = resultado.get('mensaje')
            conexion.save()
            return Response({'ok': False, 'mensaje': resultado.get('mensaje')}, status=status.HTTP_400_BAD_REQUEST)
        data = resultado.get('data') or {}
        conexion.display_phone_number = data.get('display_phone_number')
        conexion.verified_name = data.get('verified_name')
        conexion.estado = CtnWhatsappConexion.ESTADO_ACTIVO
        conexion.error_mensaje = None
        conexion.save()
        return Response({'ok': True, 'data': data})
