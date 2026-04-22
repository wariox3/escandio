import logging
from django.db import connection, transaction
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from contenedor.models import Contenedor, CtnWhatsappConexion
from mensajeria.models import MsjConversacion, MsjMensaje
from mensajeria.serializers.conversacion import MsjConversacionSerializador
from mensajeria.serializers.mensaje import MsjMensajeSerializador
from mensajeria.servicios.whatsapp_cliente import WhatsappCliente

logger = logging.getLogger(__name__)


class MsjConversacionViewSet(viewsets.ModelViewSet):
    queryset = MsjConversacion.objects.all()
    serializer_class = MsjConversacionSerializador
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['estado', 'asignada_a']
    ordering_fields = ['ultimo_mensaje_fecha', 'id', 'no_leidos']

    def _obtener_conexion(self):
        contenedor = Contenedor.objects.filter(schema_name=connection.schema_name).first()
        if not contenedor:
            return None
        return CtnWhatsappConexion.objects.filter(
            contenedor=contenedor,
            estado=CtnWhatsappConexion.ESTADO_ACTIVO,
        ).first()

    @action(detail=True, methods=['get'])
    def mensajes(self, request, pk=None):
        conversacion = self.get_object()
        mensajes = conversacion.mensajes.all().order_by('id')
        serializer = MsjMensajeSerializador(mensajes, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='marcar-leido')
    def marcar_leido(self, request, pk=None):
        conversacion = self.get_object()
        conversacion.no_leidos = 0
        conversacion.save(update_fields=['no_leidos', 'fecha_actualizacion'])
        return Response({'ok': True})

    @action(detail=True, methods=['post'])
    def cerrar(self, request, pk=None):
        conversacion = self.get_object()
        conversacion.estado = MsjConversacion.ESTADO_CERRADA
        conversacion.save(update_fields=['estado', 'fecha_actualizacion'])
        return Response(self.get_serializer(conversacion).data)

    @action(detail=True, methods=['post'])
    def reabrir(self, request, pk=None):
        conversacion = self.get_object()
        conversacion.estado = MsjConversacion.ESTADO_ABIERTA
        conversacion.save(update_fields=['estado', 'fecha_actualizacion'])
        return Response(self.get_serializer(conversacion).data)

    @action(detail=True, methods=['post'])
    def enviar(self, request, pk=None):
        """
        Payload: { "tipo": "texto"|"imagen"|"template", "contenido": "...",
                   "media_url": "...", "caption": "...",
                   "plantilla_nombre": "...", "plantilla_idioma": "es",
                   "plantilla_variables": [...] }
        """
        conversacion = self.get_object()
        conexion = self._obtener_conexion()
        if not conexion:
            return Response({'detail': 'Sin conexión WhatsApp activa'}, status=status.HTTP_400_BAD_REQUEST)

        datos = request.data
        tipo = datos.get('tipo', 'texto')
        cliente = WhatsappCliente(conexion)

        if tipo == 'texto':
            texto = (datos.get('contenido') or '').strip()
            if not texto:
                return Response({'contenido': ['Requerido']}, status=status.HTTP_400_BAD_REQUEST)
            resultado = cliente.enviar_texto(conversacion.cliente_telefono, texto)
            contenido_guardar, media_url, caption = texto, None, None
            tipo_modelo = MsjMensaje.TIPO_TEXTO
        elif tipo == 'imagen':
            media_url = (datos.get('media_url') or '').strip()
            caption = datos.get('caption') or None
            if not media_url:
                return Response({'media_url': ['Requerido']}, status=status.HTTP_400_BAD_REQUEST)
            resultado = cliente.enviar_imagen(conversacion.cliente_telefono, media_url, caption)
            contenido_guardar = caption
            tipo_modelo = MsjMensaje.TIPO_IMAGEN
        elif tipo == 'template':
            nombre = (datos.get('plantilla_nombre') or '').strip()
            idioma = datos.get('plantilla_idioma') or 'es'
            variables = datos.get('plantilla_variables') or []
            if not nombre:
                return Response({'plantilla_nombre': ['Requerido']}, status=status.HTTP_400_BAD_REQUEST)
            resultado = cliente.enviar_plantilla(conversacion.cliente_telefono, nombre, idioma, variables)
            textos_conocidos = {
                'hello_world': 'Hello World!',
            }
            contenido_guardar = textos_conocidos.get(nombre) or f'Plantilla enviada: {nombre}'
            media_url, caption = None, None
            tipo_modelo = MsjMensaje.TIPO_TEMPLATE
        else:
            return Response({'tipo': ['Valor no soportado']}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            msj = MsjMensaje.objects.create(
                conversacion=conversacion,
                direccion=MsjMensaje.DIRECCION_SALIDA,
                tipo=tipo_modelo,
                contenido=contenido_guardar,
                media_url=media_url,
                media_caption=caption,
                whatsapp_message_id=resultado.get('message_id'),
                estado=MsjMensaje.ESTADO_ENVIADO if not resultado['error'] else MsjMensaje.ESTADO_ERROR,
                error_mensaje=resultado.get('mensaje') if resultado['error'] else None,
                enviado_por=request.user if request.user.is_authenticated else None,
                metadata=resultado.get('raw'),
            )
            conversacion.ultimo_mensaje_fecha = timezone.now()
            conversacion.save(update_fields=['ultimo_mensaje_fecha', 'fecha_actualizacion'])

        if resultado['error']:
            return Response(
                {'ok': False, 'mensaje': resultado.get('mensaje'), 'mensaje_id': msj.id},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({'ok': True, 'mensaje_id': msj.id, 'whatsapp_message_id': resultado.get('message_id')})
