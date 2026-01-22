from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from decouple import config 
import random
import logging

logger = logging.getLogger('django')

@api_view(['GET'])
def enviar_coreo(request):
    return Response({"message": "Hello, world!"})

class PruebaView(APIView):
    def get(self, request):
        numero = 123  
        return Response("Esta es la respuesta" + numero)

