from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from general.models.configuracion import GenConfiguracion
from general.serializers.configuracion import GenConfiguracionSerializador

class ConfiguracionViewSet(viewsets.ModelViewSet):
    queryset = GenConfiguracion.objects.all()
    serializer_class = GenConfiguracionSerializador    
    permission_classes = [permissions.IsAuthenticated]

    
    @action(detail=False, methods=["post"], url_path=r'consulta',)
    def cosulta(self, request):
        raw = request.data
        campos = raw.get('campos')
        if campos:
            configuracion = GenConfiguracion.objects.filter(pk=1).values(*campos)
            return Response({'configuracion': list(configuracion)}, status=status.HTTP_200_OK)   
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)