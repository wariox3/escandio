from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from general.models.archivo import GenArchivo
from general.serializers.archivo import GenArchivoSerializador
from utilidades.utilidades import Utilidades
from utilidades.backblaze import Backblaze
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from general.filters.archivo import ArchivoFilter
from utilidades.excel_exportar import ExcelExportar
from django.http import HttpResponse
from io import BytesIO

class ArchivoViewSet(viewsets.ModelViewSet):
    queryset = GenArchivo.objects.all()
    serializer_class = GenArchivoSerializador
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = ArchivoFilter 
    serializadores = {'lista': GenArchivoSerializador}

    def get_serializer_class(self):
        serializador_parametro = self.request.query_params.get('serializador', None)
        if not serializador_parametro or serializador_parametro not in self.serializadores:
            return GenArchivoSerializador
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

    def destroy(self, request, *args, **kwargs):        
        instance = self.get_object()
        backblaze = Backblaze()
        backblaze.eliminar(instance.almacenamiento_id)    
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # Refactorizar este método para usar archivo_servicio.py
    @action(detail=False, methods=["post"], url_path=r'cargar',)
    def cargar(self, request):
        raw = request.data        
        archivo_base64 = raw.get('archivo_base64')
        nombre_archivo = raw.get('nombre_archivo')
        documento_id = raw.get('documento_id')     
        codigo = raw.get('codigo', None)
        modelo = raw.get('modelo', None)
        if archivo_base64 and nombre_archivo and (documento_id or (codigo and modelo)):            
                
            try:                        
                tenant = request.tenant.schema_name
                objeto_base64 = Utilidades.separar_base64(archivo_base64)
                backblaze = Backblaze()
                id, tamano, tipo, uuid = backblaze.subir(objeto_base64['base64_raw'], tenant, nombre_archivo)
                archivo = GenArchivo()
                archivo.archivo_tipo_id = 1
                archivo.almacenamiento_id = id
                archivo.nombre = nombre_archivo
                archivo.tipo = tipo
                archivo.tamano = tamano
                archivo.uuid = uuid
                archivo.codigo = codigo
                archivo.modelo = modelo
                archivo.save()
                return Response({'id': str(archivo.id)}, status=status.HTTP_200_OK)                                         
            except ValueError as e:
                return Response({'mensaje': str(e), 'codigo':15}, status=status.HTTP_400_BAD_REQUEST)                                                          
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)

      
    @action(detail=False, methods=["post"], url_path=r'descargar',)
    def descargar(self, request):
        raw = request.data        
        id = raw.get('id')
        if id:
            try:
                archivo = GenArchivo.objects.get(pk=id)
                try:                                                                
                    backblaze = Backblaze()
                    contenido = backblaze.descargar(archivo.almacenamiento_id)          
                    response = HttpResponse(contenido, content_type=archivo.tipo)
                    response['Access-Control-Expose-Headers'] = 'Content-Disposition'
                    response['Content-Disposition'] = f'attachment; filename="{archivo.nombre}"'                    
                    return response                                                                                   
                except ValueError as e:
                    return Response({'mensaje': str(e), 'codigo':15}, status=status.HTTP_400_BAD_REQUEST)                                   
            except GenArchivo.DoesNotExist:
                return Response({'mensaje':'El archivo no existe', 'codigo':15}, status=status.HTTP_400_BAD_REQUEST)                        
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)        

     
          
      
    

