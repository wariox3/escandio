import re
import threading
import logging
from decouple import config
from django.db import connection
from ruteo.models.visita import RutVisita
from utilidades.globalconnect import GlobalConnect

logger = logging.getLogger(__name__)


class NotificacionServicio():

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
    def notificar_despacho_aprobado(despacho_id, schema_name=None, nombre_empresa=None):
        try:
            id_plantilla = int(config('GLOBALCONNECT_PLANTILLA_DESPACHO', default='0'))
        except (ValueError, TypeError):
            id_plantilla = 0

        if not id_plantilla:
            logger.warning('GLOBALCONNECT_PLANTILLA_DESPACHO no configurada, no se envian notificaciones WhatsApp')
            return

        if not schema_name:
            schema_name = connection.schema_name

        def enviar_mensajes():
            try:
                connection.set_schema(schema_name)
                gc = GlobalConnect()
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

                enviados = 0
                errores = 0
                for telefono, datos in destinatarios.items():
                    documentos_texto = ', '.join(datos['documentos']) if datos['documentos'] else 'N/A'

                    variables = [
                        {'type': 'text', 'text': datos['nombre']},
                        {'type': 'text', 'text': nombre_empresa or 'Ruteo.co'},
                        {'type': 'text', 'text': documentos_texto},
                    ]

                    resultado = gc.enviar_plantilla(
                        id_plantilla=id_plantilla,
                        destino=telefono,
                        variables=variables,
                    )

                    if resultado['error']:
                        errores += 1
                        logger.error(f'Despacho {despacho_id}: error enviando WhatsApp a {telefono}: {resultado["mensaje"]}')
                    else:
                        enviados += 1
                        logger.info(f'Despacho {despacho_id}: WhatsApp enviado a {telefono}, guias=[{documentos_texto}], id={resultado["id"]}')

                logger.info(f'Despacho {despacho_id}: notificaciones WhatsApp completadas. Enviados={enviados}, Errores={errores}')
            except Exception as e:
                logger.error(f'Despacho {despacho_id}: error general en notificaciones WhatsApp: {e}')

        hilo = threading.Thread(target=enviar_mensajes, daemon=True)
        hilo.start()
