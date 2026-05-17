"""Vista de configuracion de la app movil v2."""
from decouple import config
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from movil.serializers.app import AppConfigSerializer
from movil.views.base import MovilApiMixin


def _a_tupla(version):
    """Convierte '2.1.0' en (2, 1, 0) para comparar versiones."""
    try:
        return tuple(int(parte) for parte in str(version).split('.'))
    except (ValueError, AttributeError):
        return ()


class AppConfigView(MovilApiMixin, APIView):
    """Version minima soportada y si la app debe/puede actualizar.

    La app consulta este endpoint al iniciar para decidir si muestra la
    pantalla de 'actualizacion requerida'. Es publico: se consulta antes de
    autenticar. Los valores se controlan por entorno (MOVIL_VERSION_*), asi se
    puede subir el piso minimo sin un deploy de codigo.
    """
    permission_classes = [AllowAny]

    @extend_schema(responses={200: AppConfigSerializer}, tags=['app'])
    def get(self, request):
        version_minima = config('MOVIL_VERSION_MINIMA', default='2.0.0')
        version_actual = config('MOVIL_VERSION_ACTUAL', default='2.0.0')
        version_app = getattr(request, 'app_version', '') or request.headers.get('X-App-Version', '')
        tupla_app = _a_tupla(version_app)
        return Response({
            'version_minima': version_minima,
            'version_actual': version_actual,
            'actualizacion_requerida': bool(tupla_app) and tupla_app < _a_tupla(version_minima),
            'actualizacion_disponible': bool(tupla_app) and tupla_app < _a_tupla(version_actual),
        })
