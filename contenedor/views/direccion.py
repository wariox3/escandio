from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework import status
from contenedor.serializers.direccion import CtnDireccionSerializador
from contenedor.models import CtnDireccion
from contenedor.servicios.direccion import DireccionServicio
from rest_framework.decorators import action
import secrets
from decouple import config
from datetime import datetime, timedelta
from utilidades.zinc import Zinc

class DireccionViewSet(viewsets.ModelViewSet):
    queryset = CtnDireccion.objects.all()
    serializer_class = CtnDireccionSerializador

    @action(detail=False, methods=["post"], url_path=r'decodificar',)
    def decodificar_action(self, request):
        direccion = request.data.get('direccion', None)
        if direccion:            
            respuesta = DireccionServicio.decodificar(direccion)
            if respuesta['error'] == False:
                return Response(respuesta, status=status.HTTP_200_OK)
            else:
                return Response({'mensaje': respuesta['mensaje']}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'mensaje': 'Faltan parámetros', 'codigo': 1}, status=status.HTTP_400_BAD_REQUEST)         
        