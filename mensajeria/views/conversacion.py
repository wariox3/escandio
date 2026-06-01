import logging
import re
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
from contenedor.mixins import RolMixin
from ruteo.servicios.notificacion import NotificacionServicio

logger = logging.getLogger(__name__)


class MsjConversacionViewSet(RolMixin, viewsets.ModelViewSet):
    modulo = 'mensajeria'
    # mensajes y plantillas son solo lectura; resto (marcar-leido, cerrar, reabrir, enviar, iniciar) requieren editar.
    acciones_lectura = ['mensajes', 'plantillas']
    queryset = MsjConversacion.objects.all()
    serializer_class = MsjConversacionSerializador
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['estado', 'asignada_a']
    ordering_fields = ['ultimo_mensaje_fecha', 'id', 'no_leidos']

    def _obtener_conexion(self):
        # Devuelve la conexion del schema actual sin filtrar por estado, para que
        # quien llame distinga "no configurada" / "pendiente" / "error" / "activo".
        contenedor = Contenedor.objects.filter(schema_name=connection.schema_name).first()
        if not contenedor:
            return None
        return CtnWhatsappConexion.objects.filter(contenedor=contenedor).first()

    def _respuesta_si_no_activa(self, conexion):
        if conexion is None:
            return Response({
                'detail': 'WhatsApp no está configurado para este contenedor.',
                'codigo': 'whatsapp_no_configurado',
            }, status=status.HTTP_400_BAD_REQUEST)
        if conexion.estado == CtnWhatsappConexion.ESTADO_PENDIENTE:
            return Response({
                'detail': 'La conexión WhatsApp está pendiente de activación.',
                'codigo': 'whatsapp_pendiente',
            }, status=status.HTTP_400_BAD_REQUEST)
        if conexion.estado == CtnWhatsappConexion.ESTADO_ERROR:
            return Response({
                'detail': f'Conexión WhatsApp con error: {conexion.error_mensaje or "sin detalle"}',
                'codigo': 'whatsapp_error',
            }, status=status.HTTP_400_BAD_REQUEST)
        return None

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
        error = self._respuesta_si_no_activa(conexion)
        if error:
            return error

        datos = request.data
        tipo = datos.get('tipo', 'texto')
        cliente = WhatsappCliente(conexion)

        if tipo == 'texto':
            texto = (datos.get('contenido') or '').strip()
            if not texto:
                return Response({'contenido': ['Requerido']}, status=status.HTTP_400_BAD_REQUEST)
            # Validar ventana de 24h: WhatsApp solo permite texto libre dentro
            # de las 24h del ultimo mensaje del usuario. Fuera de eso, solo plantilla.
            ahora = timezone.now()
            ventana = conversacion.fecha_ventana_24h
            ventana_vencida = (
                not ventana
                or (ahora - ventana).total_seconds() > 24 * 3600
            )
            if ventana_vencida:
                horas = round((ahora - ventana).total_seconds() / 3600, 1) if ventana else None
                return Response({
                    'detail': (
                        'La ventana de 24 horas con este contacto vencio'
                        + (f' (hace {horas}h)' if horas else '')
                        + '. WhatsApp solo permite enviar plantillas pre-aprobadas. '
                          'Usa tipo="template" o espera a que el cliente escriba.'
                    ),
                    'codigo': 'ventana_24h_vencida',
                    'fecha_ventana_24h': ventana.isoformat() if ventana else None,
                }, status=status.HTTP_400_BAD_REQUEST)
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
            contenido_guardar = self._expandir_template(nombre, variables)
            media_url, caption = None, None
            tipo_modelo = MsjMensaje.TIPO_TEMPLATE
        else:
            return Response({'tipo': ['Valor no soportado']}, status=status.HTTP_400_BAD_REQUEST)

        # Truncar error_mensaje al limite del campo de DB.
        error_truncado = None
        if resultado.get('error') and resultado.get('mensaje'):
            error_truncado = str(resultado['mensaje'])[:500]

        try:
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
                    error_mensaje=error_truncado,
                    enviado_por=request.user if request.user.is_authenticated else None,
                    metadata=resultado.get('raw'),
                )
                conversacion.ultimo_mensaje_fecha = timezone.now()
                conversacion.save(update_fields=['ultimo_mensaje_fecha', 'fecha_actualizacion'])
        except Exception as e:
            # El mensaje ya salio a WhatsApp pero no se pudo guardar en DB.
            # Loguear con wamid para reconciliacion manual.
            logger.exception(
                f'Mensaje enviado a WhatsApp wamid={resultado.get("message_id")} '
                f'pero fallo guardar en DB: {e}'
            )
            return Response({
                'ok': False,
                'mensaje': 'El mensaje se envio pero no se pudo registrar. Contacta al admin.',
                'whatsapp_message_id': resultado.get('message_id'),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if resultado['error']:
            return Response(
                {'ok': False, 'mensaje': error_truncado, 'mensaje_id': msj.id},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({'ok': True, 'mensaje_id': msj.id, 'whatsapp_message_id': resultado.get('message_id')})

    def _expandir_template(self, nombre, variables):
        """Reemplaza placeholders {0}, {1} ... con las variables pasadas. Si no esta
        en el diccionario conocido, devuelve un texto generico para que el inbox
        muestre algo legible en lugar de quedarse vacio."""
        plantillas = NotificacionServicio.PLANTILLAS_TEXTO
        template = plantillas.get(nombre)
        if template and variables:
            try:
                return template.format(*variables)
            except (IndexError, KeyError):
                return template
        if template:
            return template
        if variables:
            return f'Plantilla "{nombre}" — ' + ' · '.join(str(v) for v in variables)
        return f'Plantilla "{nombre}"'

    @action(detail=False, methods=['get'])
    def plantillas(self, request):
        """Lista plantillas WhatsApp conocidas con sus variables (inferidas de los placeholders {N})."""
        items = []
        for nombre, texto in NotificacionServicio.PLANTILLAS_TEXTO.items():
            indices = sorted({int(m) for m in re.findall(r'\{(\d+)\}', texto)})
            items.append({
                'nombre': nombre,
                'idioma': 'es',
                'texto': texto,
                'variables': [
                    {'indice': i, 'nombre_sugerido': f'variable_{i + 1}'}
                    for i in indices
                ],
            })
        return Response(items)

    @action(detail=False, methods=['post'])
    def iniciar(self, request):
        """Crea o reabre conversacion contra un telefono y envia plantilla como primer mensaje.

        Payload: {telefono, nombre?, plantilla_nombre, plantilla_idioma?, plantilla_variables?[]}
        Si la conversacion se acaba de crear y Meta rechaza el envio, se borra (atomico).
        Si reusabamos una existente, NO se borra.
        """
        datos = request.data
        telefono_raw = (datos.get('telefono') or '').strip()
        telefono = NotificacionServicio.normalizar_telefono(telefono_raw)
        if not telefono:
            return Response({'detail': 'Telefono invalido'}, status=status.HTTP_400_BAD_REQUEST)

        nombre_plantilla = (datos.get('plantilla_nombre') or '').strip()
        if not nombre_plantilla:
            return Response({'plantilla_nombre': ['Requerido']}, status=status.HTTP_400_BAD_REQUEST)
        idioma = datos.get('plantilla_idioma') or 'es'
        variables = datos.get('plantilla_variables') or []

        conexion = self._obtener_conexion()
        error = self._respuesta_si_no_activa(conexion)
        if error:
            return error

        nombre_cliente = (datos.get('nombre') or '').strip() or None
        conversacion, creada = MsjConversacion.objects.get_or_create(
            cliente_telefono=telefono,
            defaults={'cliente_nombre': nombre_cliente},
        )
        if not creada and conversacion.estado == MsjConversacion.ESTADO_CERRADA:
            conversacion.estado = MsjConversacion.ESTADO_ABIERTA
            conversacion.save(update_fields=['estado', 'fecha_actualizacion'])

        cliente = WhatsappCliente(conexion)
        resultado = cliente.enviar_plantilla(telefono, nombre_plantilla, idioma, variables)

        if resultado['error']:
            # Si la creamos en esta misma request y fallo el envio, no dejar conversacion
            # huerfana en el inbox. Si reutilizabamos una existente, la respetamos.
            if creada:
                conversacion.delete()
            return Response({
                'ok': False,
                'mensaje': resultado.get('mensaje') or 'Error al enviar plantilla',
            }, status=status.HTTP_502_BAD_GATEWAY)

        contenido = self._expandir_template(nombre_plantilla, variables)
        try:
            with transaction.atomic():
                msj = MsjMensaje.objects.create(
                    conversacion=conversacion,
                    direccion=MsjMensaje.DIRECCION_SALIDA,
                    tipo=MsjMensaje.TIPO_TEMPLATE,
                    contenido=contenido,
                    whatsapp_message_id=resultado.get('message_id'),
                    estado=MsjMensaje.ESTADO_ENVIADO,
                    enviado_por=request.user if request.user.is_authenticated else None,
                    metadata=resultado.get('raw'),
                )
                conversacion.ultimo_mensaje_fecha = timezone.now()
                conversacion.save(update_fields=['ultimo_mensaje_fecha', 'fecha_actualizacion'])
        except Exception as e:
            logger.exception(
                f'Plantilla enviada a WhatsApp wamid={resultado.get("message_id")} '
                f'pero fallo guardar en DB: {e}'
            )
            return Response({
                'ok': False,
                'mensaje': 'El mensaje se envio pero no se pudo registrar. Contacta al admin.',
                'whatsapp_message_id': resultado.get('message_id'),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'ok': True,
            'conversacion_id': conversacion.id,
            'mensaje_id': msj.id,
            'whatsapp_message_id': resultado.get('message_id'),
            'creada': creada,
        })
