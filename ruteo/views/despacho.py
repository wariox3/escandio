from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from ruteo.models.despacho import RutDespacho
from ruteo.models.visita import RutVisita
from ruteo.models.vehiculo import RutVehiculo
from vertical.models.entrega import VerEntrega
from vertical.models.entrega_detalle import VerEntregaDetalle
from ruteo.servicios.visita import VisitaServicio
from ruteo.servicios.despacho import DespachoServicio
from ruteo.serializers.despacho import RutDespachoSerializador, RutDespachoTraficoSerializador
from ruteo.formatos.orden_entrega import FormatoOrdenEntrega
from ruteo.filters.despacho import DespachoFilter
from rest_framework.filters import OrderingFilter
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.http import HttpResponse
from openpyxl import Workbook
from utilidades.workbook_estilos_deprecated import WorkbookEstilos
from datetime import datetime
from django.db import transaction
from utilidades.google import Google
from utilidades.holmio import Holmio
from ruteo.servicios.notificacion import NotificacionServicio


class RutDespachoViewSet(viewsets.ModelViewSet):
    queryset = RutDespacho.objects.all()
    serializer_class = RutDespachoSerializador
    permission_classes = [permissions.IsAuthenticated]    
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = DespachoFilter   
    serializadores = {
        'trafico' : RutDespachoTraficoSerializador
    }

    def get_serializer_class(self):
        serializador_parametro = self.request.query_params.get('serializador', None)
        if not serializador_parametro or serializador_parametro not in self.serializadores:
            return RutDespachoSerializador
        return self.serializadores[serializador_parametro]

    def get_queryset(self):
        page_size = self.request.query_params.get('page_size')
        if page_size:
            if page_size != '0':
                self.pagination_class = PageNumberPagination
                self.pagination_class.page_size = int(page_size)
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
            if request.query_params.get('lista_completa', '').lower() == 'true':
                self.pagination_class = None
            return super().list(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.estado_aprobado:
            return Response({'mensaje': 'No se puede eliminar un despacho aprobado.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            RutVisita.objects.filter(despacho_id=instance.id).update(despacho=None, estado_despacho=False)
            if instance.vehiculo_id:
                RutVehiculo.objects.filter(id=instance.vehiculo_id).update(estado_asignado=False)
            self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)    
    
    @action(detail=False, methods=["post"], url_path=r'aprobar',)
    def aprobar(self, request):             
        raw = request.data
        id = raw.get('id')
        if id:
            try:                
                with transaction.atomic():               
                    despacho = RutDespacho.objects.get(pk=id)  
                    if despacho.estado_aprobado == False: 
                        entrega = VerEntrega()
                        entrega.despacho_id = despacho.id
                        entrega.fecha = despacho.fecha
                        entrega.peso = despacho.peso
                        entrega.volumen = despacho.volumen
                        entrega.tiempo_servicio = despacho.tiempo_servicio
                        entrega.tiempo_trayecto = despacho.tiempo_trayecto
                        entrega.tiempo = despacho.tiempo
                        entrega.visitas = despacho.visitas
                        entrega.visitas_entregadas = despacho.visitas_entregadas
                        entrega.contenedor_id = request.tenant.id
                        entrega.schema_name = request.tenant.schema_name
                        entrega.save()
                        visitas = RutVisita.objects.filter(despacho_id=despacho.id)
                        detalles = []
                        for visita in visitas:
                            detalles.append(VerEntregaDetalle(
                                entrega=entrega,
                                visita_id=visita.id,
                                numero=visita.numero,
                                documento=visita.documento,
                                destinatario=visita.destinatario,
                                destinatario_direccion=visita.destinatario_direccion,
                                destinatario_telefono=visita.destinatario_telefono,
                                unidades=visita.unidades,
                                peso=visita.peso,
                                volumen=visita.volumen,
                                orden=visita.orden,
                            ))
                        VerEntregaDetalle.objects.bulk_create(detalles)
                        despacho.estado_aprobado = True
                        despacho.fecha_salida = datetime.now()
                        despacho.entrega_id = entrega.id
                        despacho.save()
                    else:
                        return Response({'mensaje':'El despacho ya esta aprobado', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
                NotificacionServicio.notificar_despacho_aprobado(despacho.id, schema_name=request.tenant.schema_name, nombre_empresa=request.tenant.nombre, contenedor_id=request.tenant.id)
                return Response({'mensaje': 'Se aprobo el despacho'}, status=status.HTTP_200_OK)
            except RutDespacho.DoesNotExist:
                return Response({'mensaje':'El despacho no existe', 'codigo':15}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)     

    @action(detail=False, methods=["post"], url_path=r'terminar',)
    def terminar(self, request):
        raw = request.data
        id = raw.get('id')
        if id:
            try:
                with transaction.atomic():
                    despacho = RutDespacho.objects.get(pk=id)
                    if despacho.estado_aprobado == True:
                        if despacho.estado_terminado == False:
                            visitas = RutVisita.objects.filter(despacho_id=id, estado_entregado=False, estado_novedad=False).first()
                            if visitas:
                                return Response({'mensaje':'El despacho tiene visitas sin entregar', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
                            despacho.estado_terminado = True
                            despacho.save()
                            if despacho.vehiculo_id:
                                vehiculo = RutVehiculo.objects.get(pk=despacho.vehiculo_id)
                                vehiculo.estado_asignado = False
                                vehiculo.save()
                            return Response({'mensaje': 'Se termino el despacho'}, status=status.HTTP_200_OK)
                        else:
                            return Response({'mensaje':'El despacho ya esta terminado', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
                    else:
                        return Response({'mensaje':'El despacho no esta aprobado', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
            except RutDespacho.DoesNotExist:
                return Response({'mensaje':'El despacho no existe', 'codigo':15}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST) 

    @action(detail=False, methods=["post"], url_path=r'anular',)
    def anular(self, request):
        raw = request.data
        id = raw.get('id')
        if id:
            try:
                with transaction.atomic():
                    despacho = RutDespacho.objects.get(pk=id)
                    if despacho.estado_aprobado == True and despacho.estado_anulado == False and despacho.estado_terminado == False:
                        visitas_entregadas = RutVisita.objects.filter(despacho_id=id, estado_entregado=True).first()
                        if visitas_entregadas:
                            return Response({'mensaje':'El despacho tiene visitas entregadas', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
                        RutVisita.objects.filter(despacho_id=id).update(estado_despacho=False, despacho=None)
                        despacho.estado_anulado = True
                        despacho.estado_terminado = True
                        despacho.save()
                        if despacho.vehiculo_id:
                            vehiculo = RutVehiculo.objects.get(pk=despacho.vehiculo_id)
                            vehiculo.estado_asignado = False
                            vehiculo.save()
                        return Response({'mensaje': 'Se anulo el despacho'}, status=status.HTTP_200_OK)
                    else:
                        return Response({'mensaje':'El despacho debe estar aprobado, sin terminar y sin anular', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
            except RutDespacho.DoesNotExist:
                return Response({'mensaje':'El despacho no existe', 'codigo':15}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST) 

    @action(detail=False, methods=["post"], url_path=r'visita-adicionar',)
    def visita_adicionar(self, request):             
        raw = request.data
        id = raw.get('id')
        visita_id = raw.get('visita_id')
        trafico = raw.get('trafico', False)
        if id and visita_id:
            try:                
                despacho = RutDespacho.objects.get(pk=id)
                if despacho.estado_aprobado == True and trafico == False:
                    return Response({'mensaje':'No se puede adicionar visitas a un despacho aprobado', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
                if despacho.estado_terminado == False:
                    visita = RutVisita.objects.get(pk=visita_id)
                    if visita.estado_despacho == True: 
                        if trafico == False:
                            return Response({'mensaje':'La visita esta en otro despacho', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
                        else:
                            despacho_origen = RutDespacho.objects.get(pk=visita.despacho_id)
                            despacho_origen.peso = despacho_origen.peso - visita.peso
                            despacho_origen.volumen = despacho_origen.volumen - visita.volumen
                            despacho_origen.tiempo = despacho_origen.tiempo - visita.tiempo
                            despacho_origen.tiempo_servicio = despacho_origen.tiempo_servicio - visita.tiempo_servicio
                            despacho_origen.tiempo_trayecto = despacho_origen.tiempo_trayecto - visita.tiempo_trayecto
                            despacho_origen.visitas = despacho_origen.visitas - 1                                   
                            despacho_origen.save()                                
                    visita.despacho = despacho
                    visita.estado_despacho = True
                    visita.save()                            
                    despacho.peso = despacho.peso + visita.peso
                    despacho.volumen = despacho.volumen + visita.volumen
                    despacho.tiempo = despacho.tiempo + visita.tiempo
                    despacho.tiempo_servicio = despacho.tiempo_servicio + visita.tiempo_servicio
                    despacho.tiempo_trayecto = despacho.tiempo_trayecto + visita.tiempo_trayecto
                    despacho.visitas = despacho.visitas + 1
                    despacho.save()
                    visitas_despacho = RutVisita.objects.filter(despacho_id=despacho.id, estado_decodificado=True)
                    if visitas_despacho.count() > 1:
                        VisitaServicio.ordenar(visitas_despacho)
                    return Response({'mensaje': 'Se adiciono la visita'}, status=status.HTTP_200_OK)                              
                else:
                    return Response({'mensaje':'El despacho esta terminado', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)                        
            except RutDespacho.DoesNotExist:
                return Response({'mensaje':'El despacho no existe', 'codigo':15}, status=status.HTTP_400_BAD_REQUEST)
            except RutVisita.DoesNotExist:
                return Response({'mensaje':'La visita no existe', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)            
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path=r'trasbordar',)
    def trasbordar(self, request):             
        raw = request.data
        id = raw.get('id')
        despacho_origen_id = raw.get('despacho_origen_id')        
        if id and despacho_origen_id:
            try:          
                if id != despacho_origen_id:      
                    despacho = RutDespacho.objects.get(pk=id)
                    despacho_origen = RutDespacho.objects.get(pk=despacho_origen_id)  
                    if despacho_origen.estado_terminado == False:
                        visitas = RutVisita.objects.filter(despacho_id=despacho_origen_id, estado_entregado=False, estado_novedad=False)
                        for visita in visitas:                                                                                
                            despacho_origen.peso = despacho_origen.peso - visita.peso
                            despacho_origen.volumen = despacho_origen.volumen - visita.volumen
                            despacho_origen.tiempo = despacho_origen.tiempo - visita.tiempo
                            despacho_origen.tiempo_servicio = despacho_origen.tiempo_servicio - visita.tiempo_servicio
                            despacho_origen.tiempo_trayecto = despacho_origen.tiempo_trayecto - visita.tiempo_trayecto
                            despacho_origen.visitas = despacho_origen.visitas - 1                                   
                            despacho_origen.save()                                

                            despacho.peso = despacho.peso + visita.peso
                            despacho.volumen = despacho.volumen + visita.volumen
                            despacho.tiempo = despacho.tiempo + visita.tiempo
                            despacho.tiempo_servicio = despacho.tiempo_servicio + visita.tiempo_servicio
                            despacho.tiempo_trayecto = despacho.tiempo_trayecto + visita.tiempo_trayecto
                            despacho.visitas = despacho.visitas + 1                                   
                            despacho.save()               

                            visita.despacho = despacho
                            visita.save()
                        visitas_destino = RutVisita.objects.filter(despacho_id=despacho.id, estado_decodificado=True)
                        if visitas_destino.count() > 1:
                            VisitaServicio.ordenar(visitas_destino)
                        visitas_origen = RutVisita.objects.filter(despacho_id=despacho_origen.id, estado_decodificado=True)
                        if visitas_origen.count() > 1:
                            VisitaServicio.ordenar(visitas_origen)
                        return Response({'mensaje': 'Se trasbordaron las visitas pendientes por entrega'}, status=status.HTTP_200_OK)                            
                    else:                          
                        return Response({'mensaje':'El despacho origen no puede estar terminado', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)                       
                else:
                    return Response({'mensaje':'Los despachos deben ser diferentes', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)                    
            except RutDespacho.DoesNotExist:
                return Response({'mensaje':'El despacho no existe', 'codigo':15}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path=r'plano-semantica',)
    def plano_semantica(self, request):             
        raw = request.data
        id = raw.get('id')
        if id:
            try:                
                despacho = RutDespacho.objects.get(pk=id)    
                visitas = RutVisita.objects.filter(despacho_id=id).values('numero', 'cita_inicio', 'cita_fin').order_by('orden')
                field_names = list(visitas[0].keys()) if visitas else []
                field_names.append('orden')
                orden = 0
                wb = Workbook()
                ws = wb.active
                ws.append(field_names)
                for row in visitas:
                    orden += 1                    
                    row_data = []
                    # -1 para que no tome orden
                    for field in field_names[:-1]:
                        value = row.get(field)
                        if value is None:
                            row_data.append("")
                        elif field in ('cita_inicio', 'cita_fin') and isinstance(value, datetime):
                            row_data.append(value.strftime('%d/%m/%Y %H:%M'))
                        elif isinstance(value, datetime) and value.tzinfo is not None:
                            row_data.append(value.replace(tzinfo=None))
                        else:
                            row_data.append(value) 
                    row_data.append(orden)                       
                    ws.append(row_data)
                estilos_excel = WorkbookEstilos(wb)
                estilos_excel.aplicar_estilos()         
                response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                response['Access-Control-Expose-Headers'] = 'Content-Disposition'
                response['Content-Disposition'] = f'attachment; filename=visitas.xlsx'
                wb.save(response)
                return response
            except RutDespacho.DoesNotExist:
                return Response({'mensaje':'El despacho no existe', 'codigo':15}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)  

    @action(detail=False, methods=["post"], url_path=r'tablero-trafico',)
    def tablero_trafico(self, request): 
        despachos = RutDespacho.objects.filter(
                        estado_aprobado=True, estado_terminado=False                                               
                    )           
        return Response({'mensaje': 'Se aprobo el despacho'}, status=status.HTTP_200_OK)  
    
    @action(detail=False, methods=["post"], url_path=r'ruta',)
    def ruta_action(self, request):           
        raw = request.data
        id = raw.get('id')
        if id:
            try:                
                despacho = RutDespacho.objects.get(pk=id) 
                google = Google()
                visitas = list(RutVisita.objects.filter(despacho_id=id).order_by('orden').values('latitud', 'longitud', 'cita_inicio'))
                if visitas:
                    tiene_citas = [bool(v.get('cita_inicio')) for v in visitas]
                    respuesta = google.direcciones(visitas)
                    respuesta['tiene_citas'] = tiene_citas
                    return Response({'respuesta': respuesta}, status=status.HTTP_200_OK) 
                else:
                    return Response({'respuesta': None}, status=status.HTTP_200_OK)             
            except RutDespacho.DoesNotExist:
                return Response({'mensaje':'El despacho no existe', 'codigo':15}, status=status.HTTP_400_BAD_REQUEST)        
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path=r'regenerar-indicador-entregas',)
    def regenerar_indicador_entregas_action(self, request): 
        raw = request.data
        id = raw.get('id', None)
        cantidad = DespachoServicio.regenerar_indicador_entregas(despacho_id=id)
        return Response({'mensaje': f'Se actualizaron {cantidad} despachos'},status=status.HTTP_200_OK )    

    @action(detail=False, methods=["post"], url_path=r'nuevo-complemento',)
    def nuevo_complemento_action(self, request): 
        raw = request.data
        despacho_id = raw.get('despacho_id')        
        if despacho_id:
            holmio = Holmio()
            parametros = {
                'codigo_despacho': despacho_id
            }            
            respuesta = holmio.despacho_detalle(parametros)
            if respuesta['error'] == False: 
                despacho_complemento = respuesta['despacho']                
                vehiculo = RutVehiculo.objects.filter(placa=despacho_complemento['vehiculoPlaca']).first() 
                if vehiculo:
                    with transaction.atomic():
                        data = {
                            'vehiculo':vehiculo.id,
                            'fecha': datetime.now(),
                            'codigo_complemento': despacho_complemento['codigoDespachoPk']                         
                        }                                                                        
                        serializador = RutDespachoSerializador(data=data)
                        if serializador.is_valid():
                            despacho = serializador.save()
                            respuesta = VisitaServicio.importar_complemento(limite=300, guia_desde=None, guia_hasta=None, fecha_desde=None, fecha_hasta=None, pendiente_despacho=False, codigo_contacto=None, codigo_destino=None, codigo_zona=None, codigo_despacho=despacho_id, despacho_id=despacho.id)
                            #visitas = RutVisita.objects.filter(despacho_id=despacho.id)
                            #VisitaServicio.ubicar(visitas)
                            #VisitaServicio.ordenar(visitas) 
                            DespachoServicio.regenerar_valores(despacho)
                            return Response({'mensaje': f'Se creo el despacho con exito'}, status=status.HTTP_200_OK)
                        else:
                            return Response({'mensaje':'Errores de validación', 'codigo':14, 'validaciones': serializador.errors}, status=status.HTTP_400_BAD_REQUEST)                              
                else:
                    return Response({'mensaje':f'No existe el vehiculo {despacho_complemento["vehiculoPlaca"]}', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)            
            else:
                return Response({'mensaje':'No se pudo consultar el despacho en el complemento', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)    
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
        
    @action(detail=False, methods=["post"], url_path=r'imprimir-orden-entrega',)
    def imprimirOrdenEntrega(self, request):
        raw = request.data
        id = raw.get('despacho_id')
        if id:
            try:
                pdf = None                                     
                formato = FormatoOrdenEntrega()
                pdf = formato.generar_pdf(id)              
                nombre_archivo = f"orden_entrega{id}.pdf"       
                
                response = HttpResponse(pdf, content_type='application/pdf')
                response['Access-Control-Expose-Headers'] = 'Content-Disposition'
                response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
                return response
            except RutDespacho.DoesNotExist:
                return Response({'mensaje':'La programacion no existe', 'codigo':15}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST) 