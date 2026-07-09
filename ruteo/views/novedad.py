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
from utilidades.imagen import Imagen
from ruteo.servicios.complemento import ComplementoServicio
import base64
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

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
    LIMITE_LOTE_COMPLEMENTO = ComplementoServicio.LIMITE_LOTE
    LIMITE_INTENTOS_COMPLEMENTO = ComplementoServicio.LIMITE_INTENTOS
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
                    # .first() en vez de get(): una novedad huerfana (visita
                    # borrada) no debe dar 500; se marca resuelta igual.
                    visita = RutVisita.objects.filter(pk=novedad.visita_id).first()
                    if visita:
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
            
            # Idempotencia del reenvio del auto-sync (mismo movil_token).
            novedad = RutNovedad.objects.filter(movil_token=movil_token).first()
            if novedad:
                return Response({'id': novedad.id}, status=status.HTTP_200_OK)

            # Validar la fecha ANTES de la transaccion: una fecha malformada debe
            # dar 400 (no-retryable), no un 500 que el auto-sync reintenta en
            # bucle para siempre. Antes strptime vivia dentro del atomic y su
            # ValueError se volvia 500 opaco ("Servidor fuera de linea").
            try:
                fecha_native = datetime.strptime(fecha_texto, '%Y-%m-%d %H:%M')
            except (ValueError, TypeError):
                return Response({'mensaje': 'Formato de fecha invalido. Use YYYY-MM-DD HH:MM', 'codigo': 1}, status=status.HTTP_400_BAD_REQUEST)
            fecha = timezone.make_aware(fecha_native)

            sincronizar_complemento = False
            with transaction.atomic():
                data = {
                    'fecha': fecha,
                    'visita': visita_id,
                    'novedad_tipo': novedad_tipo_id,
                    'descripcion': descripcion,
                    'movil_token': movil_token
                }
                serializer = RutNovedadSerializador(data=data)
                if not serializer.is_valid():
                    return Response({'mensaje':'Errores de validación', 'codigo':14, 'validaciones': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
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
                # Solo LEEMOS aqui si el complemento esta habilitado; la
                # sincronizacion (HTTP externo) va DESPUES del commit, fuera del
                # lock. .first() en vez de [0] para no reventar con IndexError.
                configuracion = GenConfiguracion.objects.filter(pk=1).values('rut_sincronizar_complemento').first()
                sincronizar_complemento = bool(configuracion and configuracion['rut_sincronizar_complemento'])

            # --- Fuera de la transaccion (commit hecho): la novedad quedo
            # registrada. Lo de abajo es best-effort y su fallo NO debe tumbar
            # (500) la novedad ni sostener el lock. ---
            if sincronizar_complemento:
                try:
                    imagenes_b64 = []
                    if imagenes:
                        for imagen in imagenes:
                            imagen.seek(0)
                            file_content = imagen.read()
                            base64_encoded = base64.b64encode(file_content).decode('utf-8')
                            imagenes_b64.append({
                                'base64': base64_encoded,
                            })
                    ComplementoServicio.enviar_novedad(novedad, imagenes_b64)
                except Exception:
                    logger.exception('Fallo la sincronizacion de novedad %s con el complemento', novedad.id)

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
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)  

    @action(detail=False, methods=["post"], url_path=r'nuevo_complemento',)
    def nuevo_complemento_action(self, request):
        try:
            resultado = ComplementoServicio.sincronizar_novedades(
                reiniciar_descartadas=request.data.get('reiniciar_descartadas'),
            )
        except Exception as e:
            return Response({'mensaje': f'No fue posible conectar con el almacenamiento: {e}', 'codigo': 1}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(resultado, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path=r'nuevo_complemento/resumen',)
    def nuevo_complemento_resumen_action(self, request):
        pendientes = RutNovedad.objects.filter(nuevo_complemento=False)
        descartadas = pendientes.filter(nuevo_complemento_intentos__gte=self.LIMITE_INTENTOS_COMPLEMENTO).count()
        return Response({
            'pendientes': pendientes.count() - descartadas,
            'descartadas': descartadas,
            'lote': self.LIMITE_LOTE_COMPLEMENTO,
        }, status=status.HTTP_200_OK)



                  
        

