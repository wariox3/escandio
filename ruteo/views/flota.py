from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from ruteo.models.flota import RutFlota
from ruteo.models.vehiculo import RutVehiculo
from ruteo.serializers.flota import RutFlotaSerializador
from ruteo.filters.flota import FlotaFilter
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from django.db.models import Max
from django.db import transaction

class RutFlotaViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    queryset = RutFlota.objects.all()
    serializer_class = RutFlotaSerializador    
    filter_backends = [DjangoFilterBackend, OrderingFilter]    
    filterset_class = FlotaFilter 
    serializadores = {
        'lista': RutFlotaSerializador
    }

    def get_serializer_class(self):
        serializador_parametro = self.request.query_params.get('serializador', None)
        if not serializador_parametro or serializador_parametro not in self.serializadores:
            return RutFlotaSerializador
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

    def list(self, request, *args, **kwargs):
        if request.query_params.get('lista', '').lower() == 'true':
            self.pagination_class = None
        return super().list(request, *args, **kwargs)




    @transaction.atomic
    def create(self, request, *args, **kwargs):
        vehiculo_id = request.data.get('vehiculo')
        if not vehiculo_id:
            return Response({'error': 'vehiculo es requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            vehiculo = RutVehiculo.objects.get(id=vehiculo_id)
        except RutVehiculo.DoesNotExist:
            return Response({'error': 'Vehículo no existe.'}, status=status.HTTP_404_NOT_FOUND)

        flota = RutFlota(vehiculo=vehiculo, prioridad=0)
        flota.save()

        def actualizar_prioridad():
            with transaction.atomic():
                RutFlota.objects.select_for_update().first()  # Fuerza bloqueo
                
                max_prioridad = RutFlota.objects.aggregate(
                    max_val=Max('prioridad')
                )['max_val'] or 0
                
                RutFlota.objects.filter(id=flota.id).update(
                    prioridad=max_prioridad + 1
                )

        transaction.on_commit(actualizar_prioridad)

        serializer = self.get_serializer(flota)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    

    @action(detail=False, methods=['post'], url_path=r'cambiar-prioridad')
    def cambiar_prioridad(self, request, *args, **kwargs):
        with transaction.atomic():
            try:
                flota_id = request.data.get('id')
                nueva_prioridad = int(request.data.get('prioridad'))

                flota_actual = RutFlota.objects.select_for_update().filter(id=flota_id).first()
                if not flota_actual:
                    return Response(
                        {'error': 'La flota especificada no existe'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                total_flotas = RutFlota.objects.count()

                if nueva_prioridad < 1 or nueva_prioridad > total_flotas:
                    return Response(
                        {
                            'mensaje': f'La prioridad debe estar entre 1 y {total_flotas}',
                            'codigo': 15,
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

                flota_con_prioridad = RutFlota.objects.select_for_update().filter(
                    prioridad=nueva_prioridad
                ).exclude(id=flota_id).first()

                prioridad_actual = flota_actual.prioridad

                flota_actual.prioridad = nueva_prioridad
                flota_actual.save()

                if flota_con_prioridad:
                    flota_con_prioridad.prioridad = prioridad_actual
                    flota_con_prioridad.save()

                return Response(
                    {
                        'mensaje': 'Prioridades intercambiadas exitosamente',
                        'flota_actual': {
                            'id': flota_actual.id,
                            'nueva_prioridad': nueva_prioridad,
                            'vehiculo_id': flota_actual.vehiculo.id
                        },
                        'flota_afectada': {
                            'id': flota_con_prioridad.id if flota_con_prioridad else None,
                            'nueva_prioridad': prioridad_actual if flota_con_prioridad else None,
                            'vehiculo_id': flota_con_prioridad.vehiculo.id if flota_con_prioridad else None
                        }
                    },
                    status=status.HTTP_200_OK
                )

            except Exception as e:
                return Response(
                    {'error': f'Error al intercambiar prioridades: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )