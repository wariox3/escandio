from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from ruteo.models.ubicacion import RutUbicacion
from ruteo.serializers.ubicacion import RutUbicacionSerializador, RutUbicacionTraficoSerializador
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from ruteo.filters.ubicacion import UbicacionFilter
from ruteo.servicios.alerta import AlertaServicio
from decouple import config
import logging
import requests

logger = logging.getLogger(__name__)

class RutUbicacionViewSet(viewsets.ModelViewSet):
    queryset = RutUbicacion.objects.all()
    serializer_class = RutUbicacionSerializador
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = UbicacionFilter   
    serializadores = {
        'trafico' : RutUbicacionTraficoSerializador
    }

    def get_serializer_class(self):
        serializador_parametro = self.request.query_params.get('serializador', None)
        if not serializador_parametro or serializador_parametro not in self.serializadores:
            return RutUbicacionSerializador
        return self.serializadores[serializador_parametro]

    def get_queryset(self):
        queryset = super().get_queryset()
        serializer_class = self.get_serializer_class()        
        select_related = getattr(serializer_class.Meta, 'select_related_fields', [])
        if select_related:
            queryset = queryset.select_related(*select_related)        
        campos = serializer_class.Meta.fields        
        if campos and campos != '__all__':
            queryset = queryset.only(*campos) 
        return queryset 

    def perform_create(self, serializer):
        ubicacion = serializer.save()
        if ubicacion.despacho:
            ubicacion.despacho.fecha_ubicacion = ubicacion.fecha
            ubicacion.despacho.latitud = ubicacion.latitud
            ubicacion.despacho.longitud = ubicacion.longitud
            ubicacion.despacho.save(update_fields=['fecha_ubicacion', 'latitud', 'longitud'])
            AlertaServicio.evaluar(ubicacion)

    @staticmethod
    def _mensaje_segun_google_status(google_status):
        """Traduce el status de Google Places a un mensaje claro al usuario."""
        mapeo = {
            'ZERO_RESULTS': 'No se encontraron detalles para esta dirección. Intenta con otra.',
            'OVER_QUERY_LIMIT': 'El servicio de mapas está saturado. Intenta en unos minutos.',
            'REQUEST_DENIED': 'El servicio de mapas no está disponible. Contacta a soporte.',
            'INVALID_REQUEST': 'La dirección seleccionada ya no es válida. Vuelve a buscarla.',
            'UNKNOWN_ERROR': 'Error temporal del servicio de mapas. Intenta de nuevo.',
        }
        return mapeo.get(google_status, 'No se encontraron detalles para el lugar.')

    @action(detail=False, methods=["post"], url_path=r'autocompletar')
    def autocompletar(self, request):
        try:
            input_text = request.data.get('input', {}).get('input', '')
            if not input_text:
                return Response(
                    {'mensaje': 'El parámetro "input" es requerido', 'error': True},
                    status=status.HTTP_400_BAD_REQUEST
                )

            country = request.GET.get('country', 'co')
            api_key = config('GOOGLE_MAPS_API_KEY')
            
            url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
            params = {
                'input': input_text,
                'key': api_key,
                'components': f'country:{country}',
                'types': 'address'
            }
            
            response = requests.get(url, params=params)
            google_data = response.json()

            if google_data.get('status') != 'OK':
                return Response(
                    {'mensaje': 'No se encontraron resultados', 'error': False, 'predictions': []},
                    status=status.HTTP_200_OK
                )

            return Response({
                'mensaje': 'Proceso exitoso',
                'predictions': google_data.get('predictions', [])
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'mensaje': f'Error en el servidor: {str(e)}', 'error': True},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=["post"], url_path=r'detalle')
    def place_details(self, request):
        try:
            place_id = request.data.get('place_id', '')
            if not place_id:
                return Response(
                    {'mensaje': 'El parámetro "place_id" es requerido', 'error': True},
                    status=status.HTTP_400_BAD_REQUEST
                )

            api_key = config('GOOGLE_MAPS_API_KEY')
            
            url = "https://maps.googleapis.com/maps/api/place/details/json"
            params = {
                'place_id': place_id,
                'key': api_key,
                'fields': 'formatted_address,geometry'
            }
            
            response = requests.get(url, params=params)
            google_data = response.json()
            google_status = google_data.get('status')
            google_error = google_data.get('error_message', '')

            if google_status != 'OK':
                # Loggeamos el detalle real de Google para diagnosticar la causa
                # raiz cuando los usuarios reporten que "no llega coordenada":
                # - ZERO_RESULTS: place_id valido pero sin datos.
                # - OVER_QUERY_LIMIT: cuota diaria/por-segundo excedida.
                # - REQUEST_DENIED: key sin Places API habilitada o restringida.
                # - INVALID_REQUEST: place_id expirado o malformado.
                # - UNKNOWN_ERROR: transitorio, conviene reintentar.
                logger.warning(
                    'Google Places Details no devolvio OK | status=%s error=%s place_id=%s',
                    google_status, google_error, place_id,
                )
                mensaje_usuario = self._mensaje_segun_google_status(google_status)
                return Response(
                    {
                        'mensaje': mensaje_usuario,
                        'error': True,
                        'google_status': google_status,
                        'google_error_message': google_error,
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

            # Extraemos los datos relevantes
            result = google_data.get('result', {})
            geometry = result.get('geometry', {}).get('location', {})
            latitude = geometry.get('lat')
            longitude = geometry.get('lng')

            # Latitud y longitud son requeridas para que la direccion sirva en
            # el ruteo. Si Google las omite (place sin geometry para ese
            # tipo, como regiones administrativas), respondemos error claro
            # para que el frontend avise al usuario.
            if latitude is None or longitude is None:
                logger.warning(
                    'Google Places Details OK pero sin coordenadas | place_id=%s result_keys=%s',
                    place_id, list(result.keys()),
                )
                return Response(
                    {
                        'mensaje': 'La dirección seleccionada no tiene coordenadas disponibles. Intenta con otra.',
                        'error': True,
                        'codigo': 'sin_coordenadas',
                    },
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

            return Response({
                'mensaje': 'Proceso exitoso',
                'error': False,
                'data': {
                    'address': result.get('formatted_address', ''),
                    'latitude': latitude,
                    'longitude': longitude,
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'mensaje': f'Error en el servidor: {str(e)}', 'error': True},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )