from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from ruteo.models.novedad import RutNovedad
from ruteo.models.visita import RutVisita
from general.models.archivo import GenArchivo
from general.models.configuracion import GenConfiguracion
from ruteo.serializers.novedad import RutNovedadSerializador
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from ruteo.filters.novedad import NovedadFilter
from django.db import transaction
from django.utils import timezone
from utilidades.backblaze import Backblaze
from utilidades.holmio import Holmio
from utilidades.imagen import Imagen
import base64
from datetime import datetime

class RutNovedadViewSet(viewsets.ModelViewSet):
    queryset = RutNovedad.objects.all()
    serializer_class = RutNovedadSerializador
    permission_classes = [permissions.IsAuthenticated]  
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = NovedadFilter 

    def get_serializer_class(self):
        serializador_parametro = self.request.query_params.get('serializador', None)
        if not serializador_parametro or serializador_parametro not in self.serializadores:
            return RutNovedadSerializador
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

    @action(detail=False, methods=["post"], url_path=r'solucionar',)
    def solucionar(self, request):
        raw = request.data
        id = raw.get('id')  
        solucion = raw.get('solucion')  
        if id:
            try:
                novedad = RutNovedad.objects.get(pk=id)                            
            except RutNovedad.DoesNotExist:
                return Response({'mensaje':'La novedad no existe', 'codigo':15}, status=status.HTTP_400_BAD_REQUEST)            
            
            if novedad.estado_solucion == False:                
                with transaction.atomic():
                    novedad.estado_solucion = True
                    novedad.fecha_solucion = timezone.now() 
                    novedad.solucion = solucion
                    novedad.save()                
                    visita = RutVisita.objects.get(pk=novedad.visita_id)
                    visita.estado_novedad = False
                    visita.save(update_fields=['estado_novedad'])                        
                    if visita.despacho:
                        despacho = visita.despacho
                        despacho.visitas_novedad = despacho.visitas_novedad - 1
                        despacho.save(update_fields=['visitas_novedad'])
                    return Response({'mensaje': f'Se soluciono la novedad'}, status=status.HTTP_200_OK)
            else:
                return Response({'mensaje':'La novedad ya esta solucionada', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)    
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST) 

    @action(detail=False, methods=["post"], url_path=r'nuevo',)
    def nuevo_action(self, request):                     
        imagenes = request.FILES.getlist('imagenes')
        visita_id = request.POST.get('visita_id')
        novedad_tipo_id = request.POST.get('novedad_tipo_id')
        fecha_texto = request.POST.get('fecha')
        descripcion = request.POST.get('descripcion')
        movil_token = request.POST.get('movil_token')
        if visita_id and novedad_tipo_id and fecha_texto and movil_token:            
            try:
                visita = RutVisita.objects.get(pk=visita_id)
            except RutVisita.DoesNotExist:
                return Response({'mensaje': 'La visita no existe', 'codigo': 2}, status=status.HTTP_400_BAD_REQUEST)
            
            novedad = RutNovedad.objects.filter(movil_token=movil_token).first()
            if novedad:
                return Response({'id': novedad.id}, status=status.HTTP_200_OK)            

            with transaction.atomic():
                fecha_native = datetime.strptime(fecha_texto, '%Y-%m-%d %H:%M')
                fecha = timezone.make_aware(fecha_native)                
                data = {
                    'fecha': fecha,
                    'visita': visita_id,
                    'novedad_tipo': novedad_tipo_id,
                    'descripcion': descripcion,
                    'movil_token': movil_token
                }
                serializer = RutNovedadSerializador(data=data)
                if serializer.is_valid():
                    novedad = serializer.save()
                    visita.estado_novedad = True
                    visita.save(update_fields=['estado_novedad'])  
                    if visita.despacho:
                        despacho = visita.despacho
                        despacho.visitas_novedad = despacho.visitas_novedad + 1
                        despacho.save(update_fields=['visitas_novedad'])

                    if imagenes:
                        backblaze = Backblaze()
                        tenant = request.tenant.schema_name
                        for imagen in imagenes:
                            #file_content = imagen.read()    
                            file_content = Imagen.comprimir_imagen_jpg(imagen, calidad=20, max_width=1920)                                                             
                            nombre_archivo = f'{novedad.id}.jpg'                                                   
                            id_almacenamiento, tamano, tipo, uuid, url = backblaze.subir_data(file_content, tenant, nombre_archivo)                            
                            archivo = GenArchivo()
                            archivo.archivo_tipo_id = 2
                            archivo.almacenamiento_id = id_almacenamiento
                            archivo.nombre = nombre_archivo
                            archivo.tipo = tipo
                            archivo.tamano = tamano
                            archivo.uuid = uuid
                            archivo.codigo = novedad.id
                            archivo.modelo = "RutNovedad"
                            archivo.url = url
                            archivo.save()
                    configuracion = GenConfiguracion.objects.filter(pk=1).values('rut_sincronizar_complemento')[0]                    
                    if configuracion['rut_sincronizar_complemento']:
                        imagenes_b64 = []
                        if imagenes:                        
                            for imagen in imagenes:   
                                imagen.seek(0)    
                                file_content = imagen.read()   
                                base64_encoded = base64.b64encode(file_content).decode('utf-8')                                                    
                                imagenes_b64.append({
                                    'base64': base64_encoded,
                                })                                                                                                                                                                                                        
                        self.nuevo_complemento(novedad, imagenes_b64)
                    return Response({'id': novedad.id}, status=status.HTTP_200_OK)
                else:
                    return Response({'mensaje':'Errores de validación', 'codigo':14, 'validaciones': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)                              
                
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)  

    @action(detail=False, methods=["post"], url_path=r'nuevo_complemento',)
    def nuevo_complemento_action(self, request):   
        backblaze = Backblaze()
        novedades = RutNovedad.objects.filter(nuevo_complemento=False)                
        for novedad in novedades:
            imagenes_b64 = []
            archivos = GenArchivo.objects.filter(modelo='RutNovedad', codigo=novedad.id, archivo_tipo_id=2)
            for archivo in archivos:
                contenido = backblaze.descargar_bytes(archivo.almacenamiento_id)
                if contenido is not None:
                    contenido_base64 = base64.b64encode(contenido).decode('utf-8')                    
                    imagenes_b64.append({
                        'comprimido': True,
                        'base64': contenido_base64,
                    })                                
            self.nuevo_complemento(novedad, imagenes_b64)
        return Response({'mensaje': f'Nuevo complemento {novedades.count()}'}, status=status.HTTP_200_OK)

    def nuevo_complemento(self, novedad: RutNovedad, imagenes_b64):
        holmio = Holmio()        
        parametros = {
            'codigoGuia': novedad.visita.numero,            
            'codigoNovedadTipo': novedad.novedad_tipo_id,
            'descripcion': novedad.descripcion,
            'usuario': 'ruteo'
        }
        if imagenes_b64:
            parametros['imagenes'] = imagenes_b64                    
        respuesta = holmio.novedad(parametros)
        if respuesta['error'] == False:
            novedad.nuevo_complemento = True
            novedad.save()
        return True          



                  
        

