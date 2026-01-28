from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from general.models.empresa import GenEmpresa
from contenedor.models import Contenedor
from general.serializers.empresa import GenEmpresaSerializador, GenEmpresaActualizarSerializador
from rest_framework.decorators import action
from decouple import config
from utilidades.space_do import SpaceDo
from utilidades.utilidades import Utilidades

class EmpresaViewSet(viewsets.ModelViewSet):
    queryset = GenEmpresa.objects.all()
    serializer_class = GenEmpresaSerializador    
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request):
        if GenEmpresa.objects.filter(pk=1).exists():
            return Response({'mensaje':'Ya se creó la empresa', 'codigo':14}, status=status.HTTP_400_BAD_REQUEST)
        else:
            data = request.data
            empresaSerializador = GenEmpresaSerializador(data=request.data)
            if empresaSerializador.is_valid():
                empresaSerializador.save()                         
                return Response({'empresa': empresaSerializador.data}, status=status.HTTP_200_OK)
            return Response({'mensaje':'Errores de validacion', 'codigo':14, 'validaciones': empresaSerializador.errors}, status=status.HTTP_400_BAD_REQUEST)
        
    def update(self, request, pk=None):
        empresa = self.get_object()
        empresaSerializador = GenEmpresaActualizarSerializador(empresa, data=request.data)
        if empresaSerializador.is_valid():
            empresaSerializador.save()
            return Response({'actualizacion': True, 'empresa': empresaSerializador.data}, status=status.HTTP_201_CREATED)            
        return Response({'mensaje':'Errores en la actualizacion', 'codigo':23, 'validaciones': empresaSerializador.errors}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=["post"], url_path=r'cargar-logo',)
    def cargar_logo(self, request):
        try:
            raw = request.data
            empresa_id = raw.get('empresa_id')
            imagenB64 = raw.get('imagenB64')
            if empresa_id:
                empresa = GenEmpresa.objects.get(pk=empresa_id)
                objetoB64 = Utilidades.separar_base64(imagenB64)                            
                ruta = f"escandio/{config('ENV')}/empresa/logo_{empresa.contenedor_id}_{empresa_id}.jpg"
                spaceDo = SpaceDo()                
                spaceDo.putB64(ruta, objetoB64['base64_raw'], objetoB64['content_type'])
                empresa.imagen = ruta
                empresa.save()
                contenedor = Contenedor.objects.get(pk=empresa.contenedor_id)
                contenedor.imagen = ruta
                contenedor.save()
                return Response({'cargar':True, 'imagen':f"https://{config('DO_BUCKET')}.{config('DO_REGION')}.digitaloceanspaces.com/{ruta}"}, status=status.HTTP_200_OK)
            else: 
                return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
        except GenEmpresa.DoesNotExist:
            return Response({'mensaje':'La empresa no existe', 'codigo':15}, status=status.HTTP_404_NOT_FOUND)  

    @action(detail=False, methods=["post"], url_path=r'limpiar-logo',)
    def limpiar_logo(self, request):
        try:
            raw = request.data
            empresa_id = raw.get('empresa_id')    
            if empresa_id:
                empresa = GenEmpresa.objects.get(pk=empresa_id)                
                spaceDo = SpaceDo()
                spaceDo.eliminar(empresa.imagen)
                ruta = f"escandio/logo_defecto.jpg"
                empresa.imagen = ruta
                empresa.save()
                contenedor = Contenedor.objects.get(pk=empresa.contenedor_id)
                contenedor.imagen = ruta
                contenedor.save()                
                return Response({'limpiar':True, 'imagen':f"https://{config('DO_BUCKET')}.{config('DO_REGION')}.digitaloceanspaces.com/{empresa.imagen}"}, status=status.HTTP_200_OK)                   
            else: 
                return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
        except GenEmpresa.DoesNotExist:
            return Response({'mensaje':'La empresa no existe', 'codigo':15}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=["post"], url_path=r'rededoc_activar',)
    def rededoc_activar(self, request):
        try:
            raw = request.data
            empresa_id = raw.get('empresa_id')
            set_pruebas = raw.get('set_pruebas')
            correo_facturacion_electronica = raw.get('correo_facturacion_electronica')
            copia_correo_facturacion_electronica = raw.get('copia_correo_facturacion_electronica')
            if empresa_id and set_pruebas:                                            
                empresa = GenEmpresa.objects.get(pk=1)
                if empresa.numero_identificacion and empresa.nombre_corto and empresa.telefono and empresa.correo and empresa.ciudad and empresa.identificacion and empresa.digito_verificacion and empresa.direccion and empresa.regimen and empresa.tipo_persona:
                    if empresa.rededoc_id is None or empresa.rededoc_id == '':
                        wolframio = Wolframio()                
                        respuesta = wolframio.cuentaCrear(empresa, set_pruebas, correo_facturacion_electronica, copia_correo_facturacion_electronica)
                        if respuesta['error'] == False:
                            empresa.rededoc_id = respuesta['rededoc_id']
                            empresa.save()
                            return Response({'activar':True}, status=status.HTTP_200_OK)
                        else:
                            return Response({'mensaje':respuesta['mensaje'], 'codigo':15}, status=status.HTTP_400_BAD_REQUEST)
                    else:
                        return Response({'mensaje':'La empresa ya esta activa con id ' + str(empresa.rededoc_id), 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
                else:
                    return Response({'mensaje':'La empresa debe terner configurado tipo identificacion, numero identificacion, digito verificacion, direccion, nombre, telefono, correo, ciudad, regimen, tipo, persona', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({'mensaje':'Faltan parametros, no tiene una resolución seleccionada', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
        except GenEmpresa.DoesNotExist:
            return Response({'mensaje': 'La empresa no existe', 'codigo': 15}, status=status.HTTP_400_BAD_REQUEST)
        
    @action(detail=False, methods=["post"], url_path=r'rededoc_detalle',)
    def rededoc_detalle(self, request):
        try:
            raw = request.data
            empresa_id = raw.get('empresa_id')
            if empresa_id:
                empresa = GenEmpresa.objects.get(pk=1)
                if empresa.rededoc_id is not None:
                    wolframio = Wolframio()
                    respuesta = wolframio.cuentaDetalle(empresa.rededoc_id)
                    if respuesta['error'] == False:
                        return Response({'cuenta': respuesta['cuenta']}, status=status.HTTP_200_OK)
                    else:
                        return Response({'mensaje':respuesta['mensaje'], 'codigo':15}, status=status.HTTP_400_BAD_REQUEST)
                else:
                    return Response({'mensaje':'La empresa no esta activa en rededoc', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({'mensaje':'Faltan parametros, no tiene una resolución seleccionada', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
        except GenEmpresa.DoesNotExist:
            return Response({'mensaje': 'La empresa no existe', 'codigo': 15}, status=status.HTTP_400_BAD_REQUEST)     

    @action(detail=False, methods=["post"], url_path=r'rededoc_actualizar',)
    def rededoc_actualizar(self, request):
        try:
            raw = request.data
            empresa_id = raw.get('empresa_id')
            correo_facturacion_electronica = raw.get('correo_facturacion_electronica')
            copia_correo_facturacion_electronica = raw.get('copia_correo_facturacion_electronica')
            if empresa_id:                                            
                wolframio = Wolframio()
                respuesta = wolframio.cuentaActualizar(correo_facturacion_electronica, copia_correo_facturacion_electronica)
                if respuesta['error'] == False:
                    return Response({'Actualizar':True}, status=status.HTTP_200_OK)
                else:
                    return Response({'mensaje':respuesta['mensaje'], 'codigo':15}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({'mensaje':'Faltan parametros, no tiene una resolución seleccionada', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
        except GenEmpresa.DoesNotExist:
            return Response({'mensaje': 'La empresa no existe', 'codigo': 15}, status=status.HTTP_400_BAD_REQUEST)   

    @action(detail=False, methods=["post"], url_path=r'terminar-asistente',)
    def terminar_asistente(self, request):
        try:
            raw = request.data 
            empresa = GenEmpresa.objects.get(pk=1)
            if empresa.asistente_electronico == False:                                                      
                empresa.asistente_electronico = True
                empresa.save()
                return Response({'asistente_terminado':True}, status=status.HTTP_200_OK)
            else:
                return Response({'mensaje': 'El asistente ya esta terminado', 'codigo': 15}, status=status.HTTP_400_BAD_REQUEST)
        except GenEmpresa.DoesNotExist:
            return Response({'mensaje': 'La empresa no existe', 'codigo': 15}, status=status.HTTP_400_BAD_REQUEST)                
        

    @action(detail=False, methods=["post"], url_path=r'terminar-asistente-predeterminado',)
    def terminar_asistente_predeterminado(self, request):
        try:
            raw = request.data 
            empresa = GenEmpresa.objects.get(pk=1)
            if empresa.asistente_predeterminado == False:                                                      
                empresa.asistente_predeterminado = True
                empresa.save()
                return Response({'asistente_predeterminado_terminado':True}, status=status.HTTP_200_OK)
            else:
                return Response({'mensaje': 'El asistente ya esta terminado', 'codigo': 15}, status=status.HTTP_400_BAD_REQUEST)
        except GenEmpresa.DoesNotExist:
            return Response({'mensaje': 'La empresa no existe', 'codigo': 15}, status=status.HTTP_400_BAD_REQUEST)            