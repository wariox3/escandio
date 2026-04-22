import logging
import re
from datetime import timedelta
from django.db import connection, transaction
from django.utils import timezone
from contenedor.models import CtnWhatsappConexion
from mensajeria.models import MsjConversacion, MsjMensaje

logger = logging.getLogger(__name__)


class WebhookServicio:
    """
    Procesa payloads entrantes de Meta WhatsApp Cloud API.
    Estructura esperada (simplificada):
        {
          "entry": [{
            "changes": [{
              "value": {
                "metadata": {"phone_number_id": "..."},
                "messages": [...],     # mensajes del cliente
                "statuses": [...],     # estados de mensajes salientes
                "contacts": [...]
              }
            }]
          }]
        }
    """

    @staticmethod
    def _normalizar_telefono(telefono):
        if not telefono:
            return None
        numero = re.sub(r'[^\d]', '', telefono)
        if numero.startswith('57') and len(numero) >= 12:
            return numero
        if numero.startswith('3') and len(numero) == 10:
            return f'57{numero}'
        return numero if len(numero) >= 10 else None

    @classmethod
    def procesar(cls, payload):
        resultados = []
        for entry in payload.get('entry', []):
            for change in entry.get('changes', []):
                value = change.get('value') or {}
                metadata = value.get('metadata') or {}
                phone_number_id = metadata.get('phone_number_id')
                if not phone_number_id:
                    continue

                conexion = CtnWhatsappConexion.objects.select_related('contenedor').filter(
                    phone_number_id=phone_number_id,
                    estado=CtnWhatsappConexion.ESTADO_ACTIVO,
                ).first()
                if not conexion:
                    logger.warning(f'Webhook: phone_number_id={phone_number_id} sin conexion activa')
                    continue

                schema_name = conexion.contenedor.schema_name
                try:
                    connection.set_schema(schema_name)
                    if value.get('messages'):
                        for mensaje in value['messages']:
                            resultado = cls._procesar_mensaje_entrante(mensaje, value)
                            resultados.append(resultado)
                    if value.get('statuses'):
                        for estado in value['statuses']:
                            resultado = cls._procesar_estado(estado)
                            resultados.append(resultado)
                finally:
                    connection.set_schema_to_public()
        return resultados

    @classmethod
    def _procesar_mensaje_entrante(cls, mensaje, value):
        telefono = cls._normalizar_telefono(mensaje.get('from'))
        if not telefono:
            return {'ok': False, 'motivo': 'telefono invalido'}

        contactos = value.get('contacts') or []
        cliente_nombre = None
        if contactos:
            perfil = contactos[0].get('profile') or {}
            cliente_nombre = perfil.get('name')

        tipo_mensaje = mensaje.get('type', 'texto')
        contenido = None
        media_url = None
        media_caption = None

        if tipo_mensaje == 'text':
            contenido = (mensaje.get('text') or {}).get('body')
            tipo_modelo = MsjMensaje.TIPO_TEXTO
        elif tipo_mensaje == 'image':
            img = mensaje.get('image') or {}
            media_url = img.get('id')
            media_caption = img.get('caption')
            tipo_modelo = MsjMensaje.TIPO_IMAGEN
        elif tipo_mensaje == 'audio':
            media_url = (mensaje.get('audio') or {}).get('id')
            tipo_modelo = MsjMensaje.TIPO_AUDIO
        elif tipo_mensaje == 'document':
            doc = mensaje.get('document') or {}
            media_url = doc.get('id')
            media_caption = doc.get('caption') or doc.get('filename')
            tipo_modelo = MsjMensaje.TIPO_DOCUMENTO
        elif tipo_mensaje == 'location':
            loc = mensaje.get('location') or {}
            contenido = f'{loc.get("latitude")},{loc.get("longitude")}'
            tipo_modelo = MsjMensaje.TIPO_UBICACION
        else:
            tipo_modelo = MsjMensaje.TIPO_TEXTO
            contenido = f'[tipo no soportado: {tipo_mensaje}]'

        ahora = timezone.now()
        with transaction.atomic():
            conversacion, _ = MsjConversacion.objects.get_or_create(
                cliente_telefono=telefono,
                defaults={
                    'cliente_nombre': cliente_nombre,
                    'visita_id': cls._buscar_visita_activa(telefono),
                },
            )
            if cliente_nombre and not conversacion.cliente_nombre:
                conversacion.cliente_nombre = cliente_nombre
            if conversacion.estado == MsjConversacion.ESTADO_CERRADA:
                conversacion.estado = MsjConversacion.ESTADO_ABIERTA
            conversacion.ultimo_mensaje_fecha = ahora
            conversacion.fecha_ventana_24h = ahora
            conversacion.no_leidos = (conversacion.no_leidos or 0) + 1
            conversacion.save()

            msj = MsjMensaje.objects.create(
                conversacion=conversacion,
                direccion=MsjMensaje.DIRECCION_ENTRADA,
                tipo=tipo_modelo,
                contenido=contenido,
                whatsapp_message_id=mensaje.get('id'),
                estado=MsjMensaje.ESTADO_ENTREGADO,
                media_url=media_url,
                media_caption=media_caption,
                metadata=mensaje,
            )
        return {'ok': True, 'mensaje_id': msj.id, 'conversacion_id': conversacion.id}

    @classmethod
    def _procesar_estado(cls, estado):
        wamid = estado.get('id')
        nuevo_estado = estado.get('status')
        mapping = {
            'sent': MsjMensaje.ESTADO_ENVIADO,
            'delivered': MsjMensaje.ESTADO_ENTREGADO,
            'read': MsjMensaje.ESTADO_LEIDO,
            'failed': MsjMensaje.ESTADO_ERROR,
        }
        estado_modelo = mapping.get(nuevo_estado)
        if not wamid or not estado_modelo:
            return {'ok': False, 'motivo': 'estado sin id o mapeo'}
        actualizados = MsjMensaje.objects.filter(whatsapp_message_id=wamid).update(estado=estado_modelo)
        return {'ok': True, 'wamid': wamid, 'actualizados': actualizados, 'estado': estado_modelo}

    @staticmethod
    def _buscar_visita_activa(telefono):
        """Busca una visita del tenant con ese teléfono en los últimos 3 días sin entregar."""
        try:
            from ruteo.models.visita import RutVisita
            fecha_limite = timezone.now() - timedelta(days=3)
            visita = RutVisita.objects.filter(
                destinatario_telefono__icontains=telefono[-10:],
                fecha__gte=fecha_limite,
                estado_entregado=False,
            ).order_by('-fecha').values('id').first()
            return visita['id'] if visita else None
        except Exception as e:
            logger.warning(f'Error buscando visita para {telefono}: {e}')
            return None
