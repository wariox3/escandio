import re
import threading
import logging
from decimal import Decimal
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
        'entrega': (
            '¡Hola, {0}! 👋 En {1} tenemos un paquete 📦 para ti, con número de guía {2}, '
            'ya está en ruta 🚚. Nuestro conductor realizará la entrega hoy durante el día '
            'en la dirección registrada. La entrega se hará dentro del horario de reparto, '
            'por lo que te recomendamos estar pendiente de recibirla. Si en el momento de la '
            'visita no es posible realizar la entrega, se programará un nuevo intento. '
            '¡Gracias por tu atención! 😁'
        ),
        'entrega_tarifa': (
            '¡Hola, {0}! 👋 En {1} tenemos un paquete 📦 para ti, con número de guía {2}, '
            'ya está en ruta 🚚. El valor a pagar al recibir es ${3}. Te recomendamos tener '
            'listo el monto exacto. ¡Gracias por tu atención! 😁'
        ),
        'en_camino': (
            '¡Hola, {0}! 🚚 Tu pedido {1} salió hacia tu dirección. Te avisaremos cuando '
            'esté cerca. ¡Mantente pendiente! 📦'
        ),
        'proximo': (
            '¡Hola, {0}! 📍 Tu pedido {1} llegará en aproximadamente {2} minutos. Por favor '
            'mantente atento para recibirlo. 🚚'
        ),
        'entregado': (
            '¡Hola, {0}! ✅ Tu pedido {1} fue entregado correctamente. Gracias por confiar '
            'en {2}. ¡Esperamos verte pronto! 😁'
        ),
        'novedad': (
            '¡Hola, {0}! ⚠️ Hubo una novedad con tu pedido {1}: {2}. Nuestro equipo te '
            'contactará pronto para coordinar. Gracias por tu paciencia. 🙏'
        ),
        'reagendar': (
            '¡Hola, {0}! 📅 Tu pedido {1} se reprogramó para {2}. Disculpa los inconvenientes. '
            '¡Estaremos pendientes de tu entrega! 🚚'
        ),
        'consulta_horario': (
            '¡Hola, {0}! 👋 Somos {1}. ¿En qué horario te queda mejor recibir tu pedido {2}? '
            'Por favor responde este mensaje con tu horario preferido para coordinar la entrega. 📅'
        ),
    }

    @staticmethod
    def _formatear_tarifa(tarifa):
        """Formatea un Decimal/float a texto con separador de miles estilo CO.
        Ejemplos: 15000 -> '15.000', 1500.5 -> '1.501', 0 -> '0'."""
        try:
            entero = int(round(float(tarifa)))
        except (TypeError, ValueError):
            return str(tarifa)
        # Formato 1234567 -> '1.234.567'
        return f'{entero:,}'.replace(',', '.')

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
    def _diagnosticar_envio(contenedor_id, schema_name):
        """Devuelve (puede_enviar, razon, conexion).

        razon es uno de: 'ok', 'sin_contenedor_id', 'contenedor_no_existe',
        'acceso_whatsapp_notificaciones_off', 'sin_conexion_activa',
        'tenant_whatsapp_off'.

        Usado por el endpoint aprobar para reportar al usuario por que las
        notificaciones no salieron, en lugar de fallar silenciosamente.
        """
        if not contenedor_id:
            return False, 'sin_contenedor_id', None
        try:
            contenedor = Contenedor.objects.get(pk=contenedor_id)
        except Contenedor.DoesNotExist:
            return False, 'contenedor_no_existe', None
        if not contenedor.acceso_whatsapp_notificaciones:
            return False, 'acceso_whatsapp_notificaciones_off', None
        conexion = CtnWhatsappConexion.objects.filter(
            contenedor=contenedor,
            estado=CtnWhatsappConexion.ESTADO_ACTIVO,
        ).first()
        if not conexion:
            return False, 'sin_conexion_activa', None
        # Validar tambien la flag del tenant. Como esto corre en schema public
        # (request.tenant resuelto), tenemos que cambiar de schema temporalmente.
        schema_a_usar = schema_name or connection.schema_name
        try:
            connection.set_schema(schema_a_usar)
            cfg = GenConfiguracion.objects.filter(pk=1).values_list(
                'rut_whatsapp_habilitado', flat=True
            ).first()
        finally:
            connection.set_schema_to_public()
        if not cfg:
            return False, 'tenant_whatsapp_off', None
        return True, 'ok', conexion

    RAZONES_HUMANAS = {
        'ok': None,
        'sin_contenedor_id': 'No se identificó el contenedor.',
        'contenedor_no_existe': 'El contenedor no existe.',
        'acceso_whatsapp_notificaciones_off': 'El contenedor no tiene WhatsApp habilitado para notificaciones.',
        'sin_conexion_activa': 'No hay conexión de WhatsApp activa. Configurala desde Mensajería → WhatsApp.',
        'tenant_whatsapp_off': 'WhatsApp deshabilitado en la configuración del contenedor (Configuración → WhatsApp).',
    }

    @staticmethod
    def notificar_despacho_aprobado(despacho_id, schema_name=None, nombre_empresa=None, contenedor_id=None):
        """Dispara las notificaciones de WhatsApp al aprobar despacho.

        Devuelve un dict con el resultado para que el endpoint pueda informar
        al usuario:
            {
              'enviado': bool,    # True si se programó el envio
              'razon': str,       # 'ok' o codigo de fallo
              'mensaje': str,     # mensaje humano
              'destinatarios': int  # cantidad estimada (solo si enviado=True)
            }
        """
        puede, razon, conexion = NotificacionServicio._diagnosticar_envio(contenedor_id, schema_name)
        if not puede:
            mensaje = NotificacionServicio.RAZONES_HUMANAS.get(razon, razon)
            logger.info(f'Despacho {despacho_id}: notificaciones omitidas — {razon}')
            return {'enviado': False, 'razon': razon, 'mensaje': mensaje, 'destinatarios': 0}

        contenedor = Contenedor.objects.get(pk=contenedor_id)
        if not schema_name:
            schema_name = connection.schema_name

        # Contar destinatarios validos (con telefono normalizable) antes de
        # disparar el thread, para reportar al endpoint.
        try:
            connection.set_schema(schema_name)
            visitas = list(RutVisita.objects.filter(
                despacho_id=despacho_id
            ).values('destinatario_telefono'))
        finally:
            connection.set_schema_to_public()
        telefonos_validos = {
            t for t in (NotificacionServicio.normalizar_telefono(v['destinatario_telefono']) for v in visitas)
            if t
        }

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
                ).values('id', 'destinatario', 'destinatario_telefono', 'documento', 'tarifa')

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
                            'tarifa_total': Decimal('0'),
                        }
                    documento = visita['documento'] or ''
                    if documento:
                        destinatarios[telefono]['documentos'].append(documento)
                    tarifa_visita = visita.get('tarifa') or 0
                    destinatarios[telefono]['tarifa_total'] += Decimal(str(tarifa_visita))

                cliente = WhatsappCliente(conexion)
                enviados = 0
                errores = 0

                for telefono, datos in destinatarios.items():
                    documentos_texto = ', '.join(datos['documentos']) if datos['documentos'] else 'N/A'

                    # Si el destinatario tiene visitas con tarifa > 0, usamos la
                    # plantilla 'entrega_tarifa' que incluye el monto a pagar.
                    # Si no, respetamos la plantilla configurada en el tenant.
                    if datos['tarifa_total'] > 0:
                        plantilla_efectiva = 'entrega_tarifa'
                        tarifa_fmt = NotificacionServicio._formatear_tarifa(datos['tarifa_total'])
                        variables = [datos['nombre'], nombre_empresa_final, documentos_texto, tarifa_fmt]
                    elif plantilla_nombre in NotificacionServicio.PLANTILLAS_SIN_VARIABLES:
                        plantilla_efectiva = plantilla_nombre
                        variables = []
                    else:
                        plantilla_efectiva = plantilla_nombre
                        variables = [datos['nombre'], nombre_empresa_final, documentos_texto]

                    resultado = cliente.enviar_plantilla(
                        telefono=telefono,
                        nombre_plantilla=plantilla_efectiva,
                        idioma=plantilla_idioma,
                        variables=variables,
                    )

                    exito = not resultado.get('error')
                    if exito:
                        enviados += 1
                        logger.info(
                            f'Despacho {despacho_id}: WhatsApp [{plantilla_efectiva}] enviado a {telefono}, '
                            f'guias=[{documentos_texto}], wamid={resultado.get("message_id")}'
                        )
                    else:
                        errores += 1
                        logger.error(
                            f'Despacho {despacho_id}: error enviando WhatsApp [{plantilla_efectiva}] a {telefono}: '
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
                        resultado=resultado,
                        variables=variables,
                        plantilla_nombre=plantilla_efectiva,
                    )

                logger.info(
                    f'Despacho {despacho_id}: notificaciones WhatsApp completadas. '
                    f'Enviados={enviados}, Errores={errores}'
                )
            except Exception as e:
                logger.exception(f'Despacho {despacho_id}: error general en notificaciones WhatsApp: {e}')

        hilo = threading.Thread(target=enviar_mensajes, daemon=True)
        hilo.start()

        return {
            'enviado': True,
            'razon': 'ok',
            'mensaje': f'Notificaciones en cola para {len(telefonos_validos)} destinatario(s).',
            'destinatarios': len(telefonos_validos),
        }

    @staticmethod
    def notificar_visita_entregada(visita_id, schema_name=None, nombre_empresa=None, contenedor_id=None):
        """Dispara plantilla 'entregado' a una visita recién entregada."""
        return NotificacionServicio._notificar_evento_visita(
            visita_id=visita_id,
            plantilla='entregado',
            armar_variables=lambda v, empresa: [
                v.get('destinatario') or 'Cliente',
                v.get('documento') or 'tu pedido',
                empresa,
            ],
            schema_name=schema_name,
            nombre_empresa=nombre_empresa,
            contenedor_id=contenedor_id,
        )

    @staticmethod
    def notificar_visita_novedad(visita_id, motivo, schema_name=None, nombre_empresa=None, contenedor_id=None):
        """Dispara plantilla 'novedad' a una visita con incidencia. `motivo` describe la novedad."""
        return NotificacionServicio._notificar_evento_visita(
            visita_id=visita_id,
            plantilla='novedad',
            armar_variables=lambda v, empresa: [
                v.get('destinatario') or 'Cliente',
                v.get('documento') or 'tu pedido',
                motivo or 'incidencia en la entrega',
            ],
            schema_name=schema_name,
            nombre_empresa=nombre_empresa,
            contenedor_id=contenedor_id,
        )

    @staticmethod
    def notificar_visita_en_camino(visita_id, schema_name=None, nombre_empresa=None, contenedor_id=None):
        """Dispara plantilla 'en_camino' a una visita: el pedido salió hacia el destinatario."""
        return NotificacionServicio._notificar_evento_visita(
            visita_id=visita_id,
            plantilla='en_camino',
            armar_variables=lambda v, empresa: [
                v.get('destinatario') or 'Cliente',
                v.get('documento') or 'tu pedido',
            ],
            schema_name=schema_name,
            nombre_empresa=nombre_empresa,
            contenedor_id=contenedor_id,
        )

    @staticmethod
    def notificar_visita_proxima(visita_id, minutos, schema_name=None, nombre_empresa=None, contenedor_id=None):
        """Dispara plantilla 'proximo' a una visita: pedido llega en X minutos."""
        try:
            min_str = str(int(round(float(minutos))))
        except (TypeError, ValueError):
            min_str = str(minutos) if minutos is not None else '5'
        return NotificacionServicio._notificar_evento_visita(
            visita_id=visita_id,
            plantilla='proximo',
            armar_variables=lambda v, empresa: [
                v.get('destinatario') or 'Cliente',
                v.get('documento') or 'tu pedido',
                min_str,
            ],
            schema_name=schema_name,
            nombre_empresa=nombre_empresa,
            contenedor_id=contenedor_id,
        )

    @staticmethod
    def notificar_visita_reagendada(visita_id, fecha_nueva, schema_name=None, nombre_empresa=None, contenedor_id=None):
        """Dispara plantilla 'reagendar' a una visita reprogramada. `fecha_nueva` es texto humano."""
        return NotificacionServicio._notificar_evento_visita(
            visita_id=visita_id,
            plantilla='reagendar',
            armar_variables=lambda v, empresa: [
                v.get('destinatario') or 'Cliente',
                v.get('documento') or 'tu pedido',
                str(fecha_nueva) if fecha_nueva else 'una nueva fecha',
            ],
            schema_name=schema_name,
            nombre_empresa=nombre_empresa,
            contenedor_id=contenedor_id,
        )

    @staticmethod
    def notificar_despacho_iniciado(despacho_id, schema_name=None, nombre_empresa=None, contenedor_id=None):
        """Dispara plantilla 'en_camino' para todas las visitas pendientes del despacho.

        Lo dispara el endpoint que marca el inicio físico de la ruta (cuando el
        conductor sale). Reporta cuántas visitas elegibles había.
        """
        puede, razon, _conexion = NotificacionServicio._diagnosticar_envio(contenedor_id, schema_name)
        if not puede:
            mensaje = NotificacionServicio.RAZONES_HUMANAS.get(razon, razon)
            logger.info(f'Despacho {despacho_id}: en_camino omitido — {razon}')
            return {'enviado': False, 'razon': razon, 'mensaje': mensaje, 'destinatarios': 0}

        if not schema_name:
            schema_name = connection.schema_name

        try:
            connection.set_schema(schema_name)
            visitas = list(RutVisita.objects.filter(
                despacho_id=despacho_id,
                estado_entregado=False,
                estado_novedad=False,
            ).values('id', 'destinatario_telefono'))
        finally:
            connection.set_schema_to_public()

        elegibles = [
            v for v in visitas
            if NotificacionServicio.normalizar_telefono(v.get('destinatario_telefono'))
        ]
        for v in elegibles:
            NotificacionServicio.notificar_visita_en_camino(
                visita_id=v['id'],
                schema_name=schema_name,
                nombre_empresa=nombre_empresa,
                contenedor_id=contenedor_id,
            )

        return {
            'enviado': True,
            'razon': 'ok',
            'mensaje': f'Notificaciones [en_camino] en cola para {len(elegibles)} visita(s).',
            'destinatarios': len(elegibles),
        }

    @staticmethod
    def _notificar_evento_visita(visita_id, plantilla, armar_variables, schema_name=None, nombre_empresa=None, contenedor_id=None):
        """Helper común para mandar una plantilla referente a UNA visita.

        `armar_variables` es callable(visita_dict, nombre_empresa) -> list[str] con
        los valores de las variables de la plantilla en el orden esperado.

        Devuelve dict similar al de notificar_despacho_aprobado.
        """
        puede, razon, conexion = NotificacionServicio._diagnosticar_envio(contenedor_id, schema_name)
        if not puede:
            mensaje = NotificacionServicio.RAZONES_HUMANAS.get(razon, razon)
            logger.info(f'Visita {visita_id}: notificacion [{plantilla}] omitida — {razon}')
            return {'enviado': False, 'razon': razon, 'mensaje': mensaje, 'destinatarios': 0}

        contenedor = Contenedor.objects.get(pk=contenedor_id)
        if not schema_name:
            schema_name = connection.schema_name
        nombre_empresa_final = nombre_empresa or contenedor.nombre or 'Ruteo.co'

        # Leer datos de la visita en el schema del tenant.
        try:
            connection.set_schema(schema_name)
            visita = RutVisita.objects.filter(pk=visita_id).values(
                'id', 'destinatario', 'destinatario_telefono', 'documento',
            ).first()
        finally:
            connection.set_schema_to_public()

        if not visita:
            logger.warning(f'Visita {visita_id}: no existe — no se notifica [{plantilla}]')
            return {'enviado': False, 'razon': 'visita_no_existe', 'mensaje': 'Visita no encontrada', 'destinatarios': 0}

        telefono = NotificacionServicio.normalizar_telefono(visita['destinatario_telefono'])
        if not telefono:
            logger.info(f'Visita {visita_id}: sin telefono valido para [{plantilla}]')
            return {'enviado': False, 'razon': 'sin_telefono', 'mensaje': 'La visita no tiene teléfono válido', 'destinatarios': 0}

        variables = armar_variables(visita, nombre_empresa_final)

        def enviar():
            try:
                connection.set_schema(schema_name)
                config_tenant = GenConfiguracion.objects.filter(pk=1).values_list(
                    'rut_whatsapp_habilitado', flat=True
                ).first()
                if not config_tenant:
                    logger.info(f'Visita {visita_id}: WhatsApp del tenant deshabilitado, no se envia [{plantilla}]')
                    return

                cliente = WhatsappCliente(conexion)
                resultado = cliente.enviar_plantilla(
                    telefono=telefono,
                    nombre_plantilla=plantilla,
                    idioma=NotificacionServicio.PLANTILLA_IDIOMA,
                    variables=variables,
                )

                exito = not resultado.get('error')
                if exito:
                    logger.info(
                        f'Visita {visita_id}: WhatsApp [{plantilla}] enviado a {telefono}, '
                        f'wamid={resultado.get("message_id")}'
                    )
                else:
                    logger.error(
                        f'Visita {visita_id}: error enviando [{plantilla}] a {telefono}: '
                        f'{resultado.get("mensaje")}'
                    )

                NotificacionServicio._registrar_en_inbox(
                    telefono=telefono,
                    nombre_cliente=visita['destinatario'] or 'Cliente',
                    resultado=resultado,
                    variables=variables,
                    plantilla_nombre=plantilla,
                )
            except Exception as e:
                logger.exception(f'Visita {visita_id}: error en notificacion [{plantilla}]: {e}')

        hilo = threading.Thread(target=enviar, daemon=True)
        hilo.start()

        return {
            'enviado': True,
            'razon': 'ok',
            'mensaje': f'Notificación [{plantilla}] en cola para {telefono}',
            'destinatarios': 1,
        }

    @staticmethod
    def _registrar_en_inbox(telefono, nombre_cliente, resultado, variables, plantilla_nombre=None):
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
