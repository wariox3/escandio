import re
import threading
import logging
from decouple import config
from django.db import connection
from django.utils import timezone
from contenedor.models import Contenedor, CtnWhatsappConexion
from general.models.configuracion import GenConfiguracion
from ruteo.models.visita import RutVisita
from ruteo.models.notificacion import RutNotificacion
from mensajeria.models import MsjConversacion, MsjMensaje
from mensajeria.servicios.whatsapp_cliente import WhatsappCliente

logger = logging.getLogger(__name__)


class NotificacionServicio():

    PLANTILLA_DESPACHO = config('META_PLANTILLA_DESPACHO', default='entrega')
    PLANTILLA_IDIOMA = config('META_PLANTILLA_DESPACHO_IDIOMA', default='es')
    # Plantillas que NO admiten variables (las mandamos sin parameters).
    PLANTILLAS_SIN_VARIABLES = {'hello_world'}
    # Texto real de las plantillas conocidas con placeholders {0},{1},... — se usa
    # para registrar en el inbox el mensaje ya expandido con las variables, asi
    # se ve "como si estuviera en operacion" en vez de "Plantilla enviada: X".
    PLANTILLAS_TEXTO = {
        'hello_world': 'Hello World!',
        'entrega': 'Hola {0}, {1} ha despachado tu pedido. Guías: {2}',
    }

    @staticmethod
    def normalizar_telefono(telefono):
        if not telefono:
            return None
        numero = re.sub(r'[^\d]', '', telefono)
        if numero.startswith('57') and len(numero) >= 12:
            return numero
        if numero.startswith('3') and len(numero) == 10:
            return f'57{numero}'
        if len(numero) == 7:
            return None
        return numero if len(numero) >= 10 else None

    @staticmethod
    def notificar_despacho_aprobado(despacho_id, schema_name=None, nombre_empresa=None, contenedor_id=None):
        if not contenedor_id:
            logger.warning(f'Despacho {despacho_id}: sin contenedor_id, no se envían notificaciones WhatsApp')
            return

        try:
            contenedor = Contenedor.objects.get(pk=contenedor_id)
        except Contenedor.DoesNotExist:
            logger.warning(f'Despacho {despacho_id}: contenedor {contenedor_id} no existe')
            return

        if not contenedor.acceso_whatsapp_notificaciones:
            logger.info(f'Despacho {despacho_id}: acceso_whatsapp_notificaciones deshabilitado para {contenedor.schema_name}')
            return

        conexion = CtnWhatsappConexion.objects.filter(
            contenedor=contenedor,
            estado=CtnWhatsappConexion.ESTADO_ACTIVO,
        ).first()
        if not conexion:
            logger.warning(f'Despacho {despacho_id}: contenedor {contenedor.schema_name} sin CtnWhatsappConexion activa')
            return

        if not schema_name:
            schema_name = connection.schema_name

        nombre_empresa_final = nombre_empresa or contenedor.nombre or 'Ruteo.co'

        def enviar_mensajes():
            try:
                connection.set_schema(schema_name)
                config_tenant = GenConfiguracion.objects.filter(pk=1).values(
                    'rut_whatsapp_habilitado',
                    'rut_whatsapp_plantilla_despacho',
                    'rut_whatsapp_plantilla_idioma',
                ).first()
                if not config_tenant or not config_tenant.get('rut_whatsapp_habilitado', False):
                    logger.info(f'Despacho {despacho_id}: WhatsApp deshabilitado por configuración del tenant')
                    return

                # Plantilla por tenant si esta seteada, sino el default global.
                plantilla_nombre = (
                    (config_tenant.get('rut_whatsapp_plantilla_despacho') or '').strip()
                    or NotificacionServicio.PLANTILLA_DESPACHO
                )
                plantilla_idioma = (
                    (config_tenant.get('rut_whatsapp_plantilla_idioma') or '').strip()
                    or NotificacionServicio.PLANTILLA_IDIOMA
                )

                visitas = RutVisita.objects.filter(
                    despacho_id=despacho_id
                ).values('id', 'destinatario', 'destinatario_telefono', 'documento')

                destinatarios = {}
                for visita in visitas:
                    telefono = NotificacionServicio.normalizar_telefono(visita['destinatario_telefono'])
                    if not telefono:
                        logger.info(f'Visita {visita["id"]}: sin telefono valido, se omite notificacion')
                        continue
                    if telefono not in destinatarios:
                        destinatarios[telefono] = {
                            'nombre': visita['destinatario'] or 'Cliente',
                            'documentos': [],
                        }
                    documento = visita['documento'] or ''
                    if documento:
                        destinatarios[telefono]['documentos'].append(documento)

                cliente = WhatsappCliente(conexion)
                enviados = 0
                errores = 0

                for telefono, datos in destinatarios.items():
                    documentos_texto = ', '.join(datos['documentos']) if datos['documentos'] else 'N/A'
                    # Plantillas como hello_world no admiten parameters; el resto si.
                    if plantilla_nombre in NotificacionServicio.PLANTILLAS_SIN_VARIABLES:
                        variables = []
                    else:
                        variables = [datos['nombre'], nombre_empresa_final, documentos_texto]

                    resultado = cliente.enviar_plantilla(
                        telefono=telefono,
                        nombre_plantilla=plantilla_nombre,
                        idioma=plantilla_idioma,
                        variables=variables,
                    )

                    exito = not resultado.get('error')
                    if exito:
                        enviados += 1
                        logger.info(
                            f'Despacho {despacho_id}: WhatsApp enviado a {telefono}, '
                            f'guias=[{documentos_texto}], wamid={resultado.get("message_id")}'
                        )
                    else:
                        errores += 1
                        logger.error(
                            f'Despacho {despacho_id}: error enviando WhatsApp a {telefono}: '
                            f'{resultado.get("mensaje")}'
                        )

                    RutNotificacion.objects.create(
                        despacho_id=despacho_id,
                        telefono=telefono,
                        estado_enviado=exito,
                    )

                    NotificacionServicio._registrar_en_inbox(
                        telefono=telefono,
                        nombre_cliente=datos['nombre'],
                        documentos_texto=documentos_texto,
                        resultado=resultado,
                        variables=variables,
                        plantilla_nombre=plantilla_nombre,
                    )

                logger.info(
                    f'Despacho {despacho_id}: notificaciones WhatsApp completadas. '
                    f'Enviados={enviados}, Errores={errores}'
                )
            except Exception as e:
                logger.exception(f'Despacho {despacho_id}: error general en notificaciones WhatsApp: {e}')

        hilo = threading.Thread(target=enviar_mensajes, daemon=True)
        hilo.start()

    @staticmethod
    def _registrar_en_inbox(telefono, nombre_cliente, documentos_texto, resultado, variables, plantilla_nombre=None):
        """Guarda el envío como MsjMensaje saliente para que quede trazabilidad en el inbox."""
        try:
            conversacion, _ = MsjConversacion.objects.get_or_create(
                cliente_telefono=telefono,
                defaults={'cliente_nombre': nombre_cliente},
            )
            if nombre_cliente and not conversacion.cliente_nombre:
                conversacion.cliente_nombre = nombre_cliente
                conversacion.save(update_fields=['cliente_nombre', 'fecha_actualizacion'])

            exito = not resultado.get('error')
            plantilla = plantilla_nombre or NotificacionServicio.PLANTILLA_DESPACHO
            # Renderizar el texto real de la plantilla con las variables sustituidas
            # para que el inbox muestre lo que el cliente realmente vio.
            texto_plantilla = NotificacionServicio.PLANTILLAS_TEXTO.get(plantilla)
            if texto_plantilla and variables:
                try:
                    contenido = texto_plantilla.format(*variables)
                except (IndexError, KeyError):
                    contenido = texto_plantilla
            elif texto_plantilla:
                contenido = texto_plantilla
            elif variables:
                contenido = f'Plantilla "{plantilla}" — ' + ' · '.join(str(v) for v in variables)
            else:
                contenido = f'Plantilla "{plantilla}"'
            MsjMensaje.objects.create(
                conversacion=conversacion,
                direccion=MsjMensaje.DIRECCION_SALIDA,
                tipo=MsjMensaje.TIPO_TEMPLATE,
                contenido=contenido,
                whatsapp_message_id=resultado.get('message_id'),
                estado=MsjMensaje.ESTADO_ENVIADO if exito else MsjMensaje.ESTADO_ERROR,
                error_mensaje=resultado.get('mensaje') if not exito else None,
                metadata={'variables': variables, 'plantilla': plantilla, 'raw': resultado.get('raw')},
            )
            conversacion.ultimo_mensaje_fecha = timezone.now()
            conversacion.save(update_fields=['ultimo_mensaje_fecha', 'fecha_actualizacion'])
        except Exception as e:
            logger.warning(f'No se pudo registrar envio en inbox para {telefono}: {e}')
