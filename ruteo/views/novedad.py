from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from ruteo.models.novedad import RutNovedad
from ruteo.models.visita import RutVisita
from general.models.archivo import GenArchivo
from general.models.configuracion import GenConfiguracion
from ruteo.serializers.novedad import RutNovedadSerializador
from ruteo.servicios.notificacion import NotificacionServicio
from ruteo.models.novedad_tipo import RutNovedadTipo
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from ruteo.filters.novedad import NovedadFilter
from contenedor.mixins import RolMixin
from django.db import transaction
from django.utils import timezone
from utilidades.backblaze import Backblaze
from utilidades.holmio import Holmio
from utilidades.imagen import Imagen
import base64
from datetime import datetime

class RutNovedadViewSet(RolMixin, viewsets.ModelViewSet):
    # RETROCOMPAT MOVIL v1.6.4 - ver contenedor/contrato_movil.py
    # /ruteo/novedad/nuevo/ y /ruteo/novedad/solucionar/ son consumidos por la
    # app movil v1.6.4 (que NO tiene perfiles), asi que quedan en
    # acciones_publicas — solo exigen IsAuthenticated. El resto del CRUD pasa
    # por PermisoModuloEditar('novedad') via RolMixin.
    modulo = 'novedad'
    acciones_publicas = ['nuevo_action', 'solucionar']
    acciones_admin = [
        'nuevo_complemento_action',
        'nuevo_complemento_resumen_action',
    ]
    LIMITE_LOTE_COMPLEMENTO = 50
    LIMITE_INTENTOS_COMPLEMENTO = 5
    queryset = RutNovedad.objects.all()
    serializer_class = RutNovedadSerializador
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

                    # Notificar al cliente la novedad. Falla silenciosa si WhatsApp
                    # no esta configurado o el tenant no lo tiene habilitado — la
                    # creacion de la novedad NO debe fallar por esto.
                    try:
                        motivo = (descripcion or '').strip()
                        if not motivo:
                            tipo_nombre = RutNovedadTipo.objects.filter(
                                pk=novedad_tipo_id
                            ).values_list('nombre', flat=True).first()
                            motivo = (tipo_nombre or 'incidencia en la entrega')
                        NotificacionServicio.notificar_visita_novedad(
                            visita_id=visita.id,
                            motivo=motivo,
                            schema_name=request.tenant.schema_name,
                            nombre_empresa=request.tenant.nombre,
                            contenedor_id=request.tenant.id,
                        )
                    except Exception:
                        pass

                    return Response({'id': novedad.id}, status=status.HTTP_200_OK)
                else:
                    return Response({'mensaje':'Errores de validación', 'codigo':14, 'validaciones': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
                
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)  

    @action(detail=False, methods=["post"], url_path=r'nuevo_complemento',)
    def nuevo_complemento_action(self, request):
        try:
            backblaze = Backblaze()
        except Exception as e:
            return Response({'mensaje': f'No fue posible conectar con el almacenamiento: {e}', 'codigo': 1}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        pendientes = RutNovedad.objects.filter(nuevo_complemento=False)
        limite_intentos = self.LIMITE_INTENTOS_COMPLEMENTO
        if request.data.get('reiniciar_descartadas'):
            pendientes.filter(nuevo_complemento_intentos__gte=limite_intentos).update(nuevo_complemento_intentos=0)
        novedades = pendientes.filter(nuevo_complemento_intentos__lt=limite_intentos)
        total_pendientes = novedades.count()
        procesadas = 0
        fallidas = []
        for novedad in novedades.select_related('visita').order_by('nuevo_complemento_intentos', 'id')[:self.LIMITE_LOTE_COMPLEMENTO]:
            try:
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
                respuesta = self.nuevo_complemento(novedad, imagenes_b64)
                if respuesta['error']:
                    fallidas.append({'id': novedad.id, 'numero': novedad.visita.numero, 'mensaje': respuesta['mensaje']})
                else:
                    procesadas += 1
            except Exception as e:
                fallidas.append({'id': novedad.id, 'numero': novedad.visita.numero, 'mensaje': str(e)})
            if procesadas == 0 and len(fallidas) >= 5:
                break
        sin_procesar = total_pendientes - procesadas - len(fallidas)
        descartadas = pendientes.filter(nuevo_complemento_intentos__gte=limite_intentos).count()
        mensaje = f'Novedad complemento: {procesadas} sincronizadas, {len(fallidas)} con error, {sin_procesar} sin procesar'
        if descartadas:
            mensaje += f', {descartadas} descartadas tras {limite_intentos} intentos'
        return Response({
            'mensaje': mensaje,
            'procesadas': procesadas,
            'fallidas': fallidas,
            'sin_procesar': sin_procesar,
            'descartadas': descartadas,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path=r'nuevo_complemento/resumen',)
    def nuevo_complemento_resumen_action(self, request):
        pendientes = RutNovedad.objects.filter(nuevo_complemento=False)
        descartadas = pendientes.filter(nuevo_complemento_intentos__gte=self.LIMITE_INTENTOS_COMPLEMENTO).count()
        return Response({
            'pendientes': pendientes.count() - descartadas,
            'descartadas': descartadas,
            'lote': self.LIMITE_LOTE_COMPLEMENTO,
        }, status=status.HTTP_200_OK)

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
            novedad.save(update_fields=['nuevo_complemento'])
            return {'error': False}
        if respuesta.get('rechazo'):
            novedad.nuevo_complemento_intentos += 1
            novedad.save(update_fields=['nuevo_complemento_intentos'])
        return respuesta



                  
        

