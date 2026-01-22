from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from general.models.empresa import GenEmpresa
import os

class PredeterminadoView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        raw = request.data
        subdominio = request.tenant.schema_name
        os.system(f"python manage.py tenant_command actualizar_fixtures general/fixtures_demanda/ --schema={subdominio}") 
        empresa = GenEmpresa.objects.get(pk=1)
        empresa.asistente_predeterminado = True
        empresa.save()
        return Response({"mensaje": "Se crearon las configuraciones por defecto"}, status=status.HTTP_200_OK)
