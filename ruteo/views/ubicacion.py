from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from ruteo.models.ubicacion import RutUbicacion
from ruteo.serializers.ubicacion import RutUbicacionSerializador, RutUbicacionTraficoSerializador
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from ruteo.filters.ubicacion import UbicacionFilter
from decouple import config
import requests

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

            if google_data.get('status') != 'OK':
                return Response(
                    {'mensaje': 'No se encontraron detalles para el lugar', 'error': True},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Extraemos los datos relevantes
            result = google_data.get('result', {})
            geometry = result.get('geometry', {}).get('location', {})
            
            return Response({
                'mensaje': 'Proceso exitoso',
                'error': False,
                'data': {
                    'address': result.get('formatted_address', ''),
                    'latitude': geometry.get('lat'),
                    'longitude': geometry.get('lng')
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'mensaje': f'Error en el servidor: {str(e)}', 'error': True},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )