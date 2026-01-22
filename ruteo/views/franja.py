from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from ruteo.models.franja import RutFranja
from ruteo.serializers.franja import RutFranjaSerializador, RutFranjaSeleccionarSerializador
from ruteo.filters.franja import FranjaFilter
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
import base64
from io import BytesIO
import openpyxl
from datetime import datetime
from decouple import config
import json
from utilidades.zinc import Zinc
from shapely.geometry import Point, Polygon
import xml.etree.ElementTree as ET
from django.core.files.base import ContentFile

def is_point_in_polygon(polygon_coords, point_coords):
    polygon = Polygon(polygon_coords)
    point = Point(point_coords)
    return polygon.contains(point)

class RutFranjaViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    queryset = RutFranja.objects.all()
    serializer_class = RutFranjaSerializador    
    filter_backends = [DjangoFilterBackend, OrderingFilter]    
    filterset_class = FranjaFilter 
    serializadores = {
        'lista': RutFranjaSerializador
    }

    def get_serializer_class(self):
        serializador_parametro = self.request.query_params.get('serializador', None)
        if not serializador_parametro or serializador_parametro not in self.serializadores:
            return RutFranjaSerializador
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
    
    @action(detail=False, methods=["get"], url_path=r'seleccionar')
    def seleccionar_action(self, request):
        limit = request.query_params.get('limit', 10)
        nombre = request.query_params.get('nombre__icontains', None)
        queryset = self.get_queryset()
        if nombre:
            queryset = queryset.filter(nombre__icontains=nombre)
        try:
            limit = int(limit)
            queryset = queryset[:limit]
        except ValueError:
            pass    
        serializer = RutFranjaSeleccionarSerializador(queryset, many=True)        
        return Response(serializer.data)         


    @action(detail=False, methods=["post"], url_path=r'importar',)
    def importar(self, request):             
        raw = request.data
        archivoB64 = raw.get('base64')
        if archivoB64:
            try:
                franjas = RutFranja.objects.all().delete()
                cantidad = 0
                archivo_decodificado = base64.b64decode(archivoB64)
                archivo_contenido = ContentFile(archivo_decodificado, "franjas.kml")
                tree = ET.parse(archivo_contenido)
                root = tree.getroot()
                namespace = {"kml": "http://www.opengis.net/kml/2.2"}                                           
                for placemark in root.findall(".//kml:Placemark", namespace):
                    nombre = placemark.find("kml:name", namespace)
                    poligono = placemark.find(".//kml:Polygon", namespace)    
                    style_url = placemark.find("kml:styleUrl", namespace)
                    color = None

                    if style_url is not None:
                        style_id = style_url.text.replace("#", "") + "-normal"                         
                        style = root.find(f".//kml:Style[@id='{style_id}']", namespace)                        
                        if style is not None:                            
                            poly_style = style.find(".//kml:PolyStyle/kml:color", namespace)
                            if poly_style is not None:
                                color = poly_style.text[2:]                        

                    if nombre is not None and poligono is not None:
                        nombre = nombre.text
                        coordinates = poligono.find(".//kml:coordinates", namespace).text.strip()                

                        coord_list = []
                        for coord in coordinates.split():
                            lon, lat, *_ = coord.split(",")
                            coord_list.append({'lat': float(lat), 'lng': float(lon)})

                        data = {
                            "codigo": nombre,
                            "nombre": nombre,
                            "coordenadas": coord_list,
                            "color": color
                        }                        
                        franja_serializador = RutFranjaSerializador(data=data)
                        if franja_serializador.is_valid():
                            franja_serializador.save()
                            cantidad += 1
                        else:
                            return Response({'validaciones':franja_serializador.errors}, status=status.HTTP_400_BAD_REQUEST)
                return Response({'mensaje': f'Se importaron {cantidad} de franjas desde el archivo kml'}, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({'mensaje':'Ocurrio un error inesperado', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)            
        else:
            return Response({'mensaje':'Faltan parametros', 'codigo':1}, status=status.HTTP_400_BAD_REQUEST)        
