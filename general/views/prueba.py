from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status
from decouple import config
import random
import logging
from utilidades.globalconnect import GlobalConnect
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
    gc = GlobalConnect()
    resultado = gc.consultar_plantillas()
    return Response(resultado)

@api_view(['POST'])
def prueba_globalconnect_enviar(request):
    telefono = request.data.get('telefono')
    nombre = request.data.get('nombre', 'Cliente prueba')
    documento = request.data.get('documento', 'GU-TEST-001')
    if not telefono:
        return Response({'mensaje': 'Falta el campo telefono'}, status=status.HTTP_400_BAD_REQUEST)
    telefono_normalizado = NotificacionServicio.normalizar_telefono(telefono)
    if not telefono_normalizado:
        return Response({'mensaje': f'Telefono invalido: {telefono}'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        id_plantilla = int(config('GLOBALCONNECT_PLANTILLA_DESPACHO', default='0'))
    except (ValueError, TypeError):
        id_plantilla = 0
    if not id_plantilla:
        return Response({'mensaje': 'GLOBALCONNECT_PLANTILLA_DESPACHO no configurada'}, status=status.HTTP_400_BAD_REQUEST)
    gc = GlobalConnect()
    variables = [
        {'type': 'text', 'text': nombre},
        {'type': 'text', 'text': documento},
        {'type': 'text', 'text': 'Ruteo.co'},
    ]
    resultado = gc.enviar_plantilla(
        id_plantilla=id_plantilla,
        destino=telefono_normalizado,
        variables=variables,
    )
    return Response({'telefono_normalizado': telefono_normalizado, 'resultado': resultado})

