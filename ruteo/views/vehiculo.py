from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from ruteo.models.vehiculo import RutVehiculo
from ruteo.models.franja import RutFranja
from ruteo.serializers.vehiculo import RutVehiculoSerializador
from ruteo.filters.vehiculo import VehiculoFilter
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
import base64
from io import BytesIO
import openpyxl
import gc

class RutVehiculoViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    queryset = RutVehiculo.objects.all()
    serializer_class = RutVehiculoSerializador    
    filter_backends = [DjangoFilterBackend, OrderingFilter]    
    filterset_class = VehiculoFilter 
    serializadores = {
        'lista': RutVehiculoSerializador
    }

    def get_serializer_class(self):
        serializador_parametro = self.request.query_params.get('serializador', None)
        if not serializador_parametro or serializador_parametro not in self.serializadores:
            return RutVehiculoSerializador
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

    def create(self, request, *args, **kwargs):
        franja_codigos = request.data.pop('franja_codigo', [])
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vehiculo = serializer.save()
        
        for codigo in franja_codigos:
            try:
                franja = RutFranja.objects.get(pk=codigo)
                vehiculo.franjas.add(franja)
            except RutFranja.DoesNotExist:
                pass
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        franja_codigos = request.data.pop('franja_codigo', [])
        
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        vehiculo = serializer.save()
        
        vehiculo.franjas.clear()
        for codigo in franja_codigos:
            try:
                franja = RutFranja.objects.get(pk=codigo)
                vehiculo.franjas.add(franja)
            except RutFranja.DoesNotExist:
                pass
        
        return Response(serializer.data)
    
    @action(detail=False, methods=["post"], url_path=r'importar',)
    def importar(self, request):
        raw = request.data        
        archivo_base64 = raw.get('archivo_base64')
        if archivo_base64:
            try:
                archivo_data = base64.b64decode(archivo_base64)
                archivo = BytesIO(archivo_data)
                wb = openpyxl.load_workbook(archivo)
                sheet = wb.active    
            except Exception as e:     
                return Response({'mensaje': 'Error procesando el archivo, valide que es un archivo de excel .xlsx', 'codigo': 15}, status=status.HTTP_400_BAD_REQUEST)  
            
            data_modelo = []
            errores = False
            errores_datos = []
            registros_importados = 0
            
            for i, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                data = {
                    'placa': row[0],
                    'capacidad': row[1],
                    'tiempo': row[2],
                    'estado_activo': True,                   
                } 
                    
                serializer = RutVehiculoSerializador(data=data)
                if serializer.is_valid():
                    vehiculo = serializer.validated_data
                    data_modelo.append((serializer.validated_data))
                else:
                    errores = True
                    error_dato = {
                        'fila': i,
                        'errores': serializer.errors
                    }                                    
                    errores_datos.append(error_dato)    

            if not errores:
                with transaction.atomic():
                    for detalle in data_modelo:
                        vehiculo = RutVehiculo.objects.create(**detalle)                
                        registros_importados += 1
                    gc.collect()
                    return Response({'registros_importados': registros_importados}, status=status.HTTP_200_OK)
            else:
                gc.collect()                    
                return Response({'mensaje': 'Errores de validación', 'codigo': 1, 'errores_validador': errores_datos}, status=status.HTTP_400_BAD_REQUEST)       
        else:
            return Response({'mensaje': 'Faltan parametros', 'codigo': 1}, status=status.HTTP_400_BAD_REQUEST)    