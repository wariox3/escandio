from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from contenedor.models import Contenedor
from contenedor.serializers.contenedor import ContenedorSerializador, ContenedorActualizarSerializador
from contenedor.serializers.usuario_contenedor import UsuarioContenedorSerializador
from general.serializers.empresa import GenEmpresaSerializador
from general.serializers.configuracion import GenConfiguracionSerializador
from contenedor.models import User
from django.core.management import call_command
from django.shortcuts import get_object_or_404
from decouple import config
from utilidades.space_do import SpaceDo
from django_tenants.utils import schema_context
import os
from datetime import datetime
from django.utils import timezone
from threading import Thread

def cargar_fixtures_en_segundo_plano(schema_name):
    """
    Función que se ejecutará en segundo plano para cargar los fixtures
    """
    try:
        with schema_context(schema_name):
            # Opción 1: Usando call_command (recomendado)
            #call_command('loaddata', 'fixture1.json', verbosity=0)
            #call_command('loaddata', 'fixture2.json', verbosity=0)
            
            # Opción 2: Manteniendo tu enfoque actual con os.system
            os.system(f"python manage.py tenant_command actualizar_fixtures general/fixtures/ --schema={schema_name}")
            os.system(f"python manage.py tenant_command actualizar_fixtures general/fixtures_inicio/ --schema={schema_name}")                
        print(f"Fixtures cargados exitosamente para {schema_name}")
    except Exception as e:
        print(f"Error cargando fixtures para {schema_name}: {str(e)}")

class ContenedorViewSet(viewsets.ModelViewSet):
    queryset = Contenedor.objects.all()
    serializer_class = ContenedorSerializador    
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(Contenedor, pk=pk)

    def create(self, request):
        try:            
            subdominio = request.data.get('subdominio')
            usuario_id = request.data.get('usuario_id')            
            nombre = request.data.get('nombre')          
            telefono = request.data.get('telefono')
            correo = request.data.get('correo')
            if subdominio and usuario_id and nombre and telefono and correo:
                contenedorValidacion = Contenedor.objects.filter(**{'schema_name':subdominio})
                if contenedorValidacion:
                    return Response({'mensaje': f"Ya existe una empresa con el nombre {subdominio}", "codigo": 13}, status=status.HTTP_400_BAD_REQUEST)
                dominio = '.' + config('DOMINIO_BACKEND')
                usuario = User.objects.get(pk=usuario_id)
                imagenReferencia = f"itrio/logo_defecto.jpg"
                call_command('create_tenant', 
                             schema_name=subdominio, 
                             domain_domain=subdominio+dominio, 
                             nombre=nombre, 
                             domain_is_primary='0', 
                             imagen=imagenReferencia,                              
                             usuarios=1,
                             usuario_id=usuario.id)  
                #os.system(f"python manage.py tenant_command actualizar_fixtures general/fixtures/ --schema={subdominio}")
                #os.system(f"python manage.py tenant_command actualizar_fixtures general/fixtures_inicio/ --schema={subdominio}")                                           
                thread = Thread(
                    target=cargar_fixtures_en_segundo_plano,
                    args=(subdominio,),
                    daemon=True
                )
                thread.start()                
                
                contenedor = Contenedor.objects.filter(**{'schema_name':subdominio}).first()                        
                data = {'usuario': usuario.id, 'contenedor': contenedor.id, 'rol': 'propietario'}
                usuarioContenedorSerializador = UsuarioContenedorSerializador(data=data)            
                if usuarioContenedorSerializador.is_valid():
                    usuarioContenedorSerializador.save()
                    with schema_context(subdominio):
                        data = {
                            'id':1,
                            'nombre_corto': nombre,
                            'telefono': telefono,
                            'correo': correo,
                            'imagen': imagenReferencia,
                            'contenedor_id':contenedor.id,
                            'subdominio':subdominio}
                        empresaSerializador = GenEmpresaSerializador(data=data)                        
                        if empresaSerializador.is_valid():
                            empresaSerializador.save()
                            data = {
                                'id':1,
                                'empresa':1,
                                'formato_factura':'F'}
                            configuracionSerializador = GenConfiguracionSerializador(data=data)                                                
                            if configuracionSerializador.is_valid():
                                configuracionSerializador.save()                            
                                return Response({'contenedor': usuarioContenedorSerializador.data}, status=status.HTTP_200_OK)            
                            return Response({'mensaje':'Errores en la creacion de la econfiguracion', 'codigo':12, 'validaciones': configuracionSerializador.errors}, status=status.HTTP_400_BAD_REQUEST)
                        return Response({'mensaje':'Errores en la creacion de la empresa', 'codigo':12, 'validaciones': empresaSerializador.errors}, status=status.HTTP_400_BAD_REQUEST)
                return Response({'mensaje':'Errores en la creacion del contenedor', 'codigo':12, 'validaciones': usuarioContenedorSerializador.errors}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'mensaje': 'Faltan datos para el consumo de la api', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)                   
        except User.DoesNotExist:
            return Response({'mensaje':'No existe el usuario para crear la empresa', 'codigo':17}, status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, pk=None):
        contenedor = self.get_object(pk)
        contenedorSerializador = self.serializer_class(contenedor)
        return Response(contenedorSerializador.data)

    def update(self, request, pk=None):
        empresa = self.get_object(pk)
        empresaSerializador = ContenedorActualizarSerializador(empresa, data=request.data)
        if empresaSerializador.is_valid():
            empresaSerializador.save()
            return Response({'actualizacion': True, 'empresa': empresaSerializador.data}, status=status.HTTP_201_CREATED)            
        return Response({'mensaje':'Errores en la actualizacion', 'codigo':23, 'validaciones': empresaSerializador.errors}, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None, *args, **kwargs):
        empresa = self.get_object(pk)        
        self.perform_destroy(empresa)
        return Response(status=status.HTTP_200_OK)
       
    @action(detail=False, methods=["post"], url_path=r'validar',)
    def validar(self, request):
        try:
            subdominio = request.data.get('subdominio')
            Contenedor.objects.get(schema_name=subdominio)
            return Response({'mensaje': f"Ya existe una empresa con el nombre {subdominio}", "codigo": 13}, status=status.HTTP_400_BAD_REQUEST)    
        except Contenedor.DoesNotExist:
            return Response({'validar':True}, status=status.HTTP_200_OK)        
        
    @action(detail=False, methods=["post"], url_path=r'cargar-logo',)
    def cargar_logo(self, request):
        try:
            raw = request.data
            empresa_id = raw.get('empresa_id')
            imagenB64 = raw.get('imagenB64')
            if empresa_id:
                empresa = Contenedor.objects.get(pk=empresa_id)
                arrDatosB64 = imagenB64.split(",")
                base64Crudo = arrDatosB64[1]
                arrTipo = arrDatosB64[0].split(";")
                arrData = arrTipo[0].split(":")
                contentType = arrData[1]
                archivo = f"itrio/{config('ENV')}/contenedor/logo_{empresa_id}.jpg"
                spaceDo = SpaceDo()
                spaceDo.putB64(archivo, base64Crudo, contentType)
                empresa.imagen = archivo
                empresa.save()
                return Response({'cargar':True, 'imagen':f"https://{config('DO_BUCKET')}.{config('DO_REGION')}.digitaloceanspaces.com/{archivo}"}, status=status.HTTP_200_OK)                  
            else: 
                return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
        except Contenedor.DoesNotExist:
            return Response({'mensaje':'La empresa no existe', 'codigo':15}, status=status.HTTP_404_NOT_FOUND)  

    @action(detail=False, methods=["post"], url_path=r'limpiar-logo',)
    def limpiar_logo(self, request):
        try:
            raw = request.data
            empresa_id = raw.get('empresa_id')    
            if empresa_id:
                empresa = Contenedor.objects.get(pk=empresa_id)                
                spaceDo = SpaceDo()
                spaceDo.eliminar(empresa.imagen)
                empresa.imagen = f"itrio/logo_defecto.jpg"
                empresa.save()
                return Response({'limpiar':True, 'imagen':f"https://{config('DO_BUCKET')}.{config('DO_REGION')}.digitaloceanspaces.com/{empresa.imagen}"}, status=status.HTTP_200_OK)                  
            else: 
                return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)
        except Contenedor.DoesNotExist:
            return Response({'mensaje':'La empresa no existe', 'codigo':15}, status=status.HTTP_404_NOT_FOUND)     

    @action(detail=False, methods=["post"], url_path=r'conectar',)
    def conectar(self, request):
        raw = request.data
        subdominio = raw.get('subdominio', None)
        if subdominio:
            try:
                contenedor = Contenedor.objects.get(schema_name=subdominio)
                contenedor.fecha_ultima_conexion = timezone.now()
                contenedor.save()
                contenedor_serializador = ContenedorSerializador(contenedor)
                return Response(contenedor_serializador.data, status=status.HTTP_200_OK)
            except Contenedor.DoesNotExist:
                return Response({'mensaje':'El contenedor no existe', 'codigo':15}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)  

                    
