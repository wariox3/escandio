import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status
from decouple import config
from django.db import connection
from contenedor.models import CtnWhatsappConexion
from mensajeria.servicios.admin_meta import AdminMetaServicio
from mensajeria.servicios.whatsapp_cliente import WhatsappCliente
from ruteo.servicios.notificacion import NotificacionServicio

logger = logging.getLogger('django')


@api_view(['GET'])
def enviar_coreo(request):
    return Response({"message": "Hello, world!"})


class PruebaView(APIView):
    def get(self, request):
        numero = 123
        return Response("Esta es la respuesta" + numero)


@api_view(['GET'])
def prueba_globalconnect_plantillas(request):
    """Lista plantillas de WhatsApp Cloud API de la WABA admin de Rutenio."""
    servicio = AdminMetaServicio()
    if not servicio._configurado():
        return Response({'mensaje': 'META_ADMIN_WABA_ID o META_ADMIN_ACCESS_TOKEN no configurados'},
                        status=status.HTTP_400_BAD_REQUEST)

    url = f'{servicio.base_url}/{servicio.waba_id}/message_templates?fields=name,status,language,category&limit=50'
    try:
        import requests
        r = requests.get(url, headers={'Authorization': f'Bearer {servicio.access_token}'}, timeout=10)
        datos = r.json() if r.content else {}
        if r.status_code == 200:
            return Response({'error': False, 'data': datos.get('data', [])})
        return Response({'error': True, 'mensaje': datos.get('error', {}).get('message') or f'HTTP {r.status_code}'},
                        status=status.HTTP_502_BAD_GATEWAY)
    except Exception as e:
        logger.exception('prueba_plantillas: error')
        return Response({'error': True, 'mensaje': str(e)}, status=status.HTTP_502_BAD_GATEWAY)


@api_view(['POST'])
def prueba_globalconnect_enviar(request):
    """
    Envía una plantilla de prueba al teléfono dado usando la conexión Meta del tenant actual.
    Body: { telefono, nombre?, documento?, plantilla? }
    """
    telefono = request.data.get('telefono')
    nombre = request.data.get('nombre', 'Cliente prueba')
    documento = request.data.get('documento', 'GU-TEST-001')
    plantilla = request.data.get('plantilla', 'entrega')
    idioma = request.data.get('idioma', 'es')

    if not telefono:
        return Response({'mensaje': 'Falta el campo telefono'}, status=status.HTTP_400_BAD_REQUEST)

    telefono_normalizado = NotificacionServicio.normalizar_telefono(telefono)
    if not telefono_normalizado:
        return Response({'mensaje': f'Telefono invalido: {telefono}'}, status=status.HTTP_400_BAD_REQUEST)

    schema = connection.schema_name
    conexion = CtnWhatsappConexion.objects.filter(
        contenedor__schema_name=schema,
        estado=CtnWhatsappConexion.ESTADO_ACTIVO,
    ).first()
    if not conexion:
        return Response({'mensaje': f'Sin conexion WhatsApp activa para el tenant {schema}'},
                        status=status.HTTP_400_BAD_REQUEST)

    cliente = WhatsappCliente(conexion)
    resultado = cliente.enviar_plantilla(
        telefono=telefono_normalizado,
        nombre_plantilla=plantilla,
        idioma=idioma,
        variables=[nombre, 'Ruteo.co', documento],
    )
    return Response({
        'telefono_normalizado': telefono_normalizado,
        'plantilla': plantilla,
        'resultado': resultado,
    })
