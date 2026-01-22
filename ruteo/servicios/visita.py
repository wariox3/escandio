from contenedor.models import CtnDireccion
from general.models.configuracion import GenConfiguracion
from ruteo.models.franja import RutFranja
from ruteo.models.visita import RutVisita
from ruteo.serializers.visita import RutVisitaSerializador
from utilidades.google import Google
from utilidades.holmio import Holmio
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from utilidades.utilidades import Utilidades
from datetime import datetime
from shapely.geometry import Point, Polygon
from math import radians, cos, sin, asin, sqrt, atan2
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from decimal import Decimal, ROUND_HALF_UP
import numpy as np
import re

class VisitaServicio():

    @staticmethod
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371.0  # Radio de la Tierra en kilómetros
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return R * c  # Retorna la distancia en kilómetros

    @staticmethod
    def construir_matriz_distancias(visitas: RutVisita, punto_inicial):
        n = len(visitas)
        matriz = np.zeros((n + 1, n + 1))  # +1 para incluir el punto de partida
        puntos = [(punto_inicial['latitud'], punto_inicial['longitud'])] + [(v.latitud, v.longitud) for v in visitas]

        for i in range(n + 1):
            for j in range(n + 1):
                matriz[i][j] = VisitaServicio.haversine(puntos[i][0], puntos[i][1], puntos[j][0], puntos[j][1])        
        return matriz

    @staticmethod
    def limpiar_direccion(direccion):
        if not direccion:
            direccion = ""
        direccion = direccion.replace("\t", "").replace("\n", "")
        direccion = re.sub(r'[\s\u2000-\u200F\u3000\u31A0]+', ' ', direccion).strip()   
        direccion = re.sub(r'[\s\u2000-\u200F\u3000\u3164]+', ' ', direccion).strip()                 
        direccion = re.sub(r'\s+', ' ', direccion.strip())                    
        direccion = direccion[:200]        
        return direccion
    
    @staticmethod
    def ubicar_punto(franjas, latitud, longitud):    
        for franja in franjas:
            coordenadas = [(coord['lng'], coord['lat']) for coord in franja.coordenadas]
            poligono = Polygon(coordenadas)                
            punto = Point(longitud, latitud)
            if poligono.contains(punto):
                return {'encontrado': True, 'franja': {'id':franja.id, 'codigo':franja.codigo}}
        return {'encontrado': False }

    @staticmethod
    def ubicar(visitas: RutVisita):    
        cantidad = 0
        franjas = RutFranja.objects.all()        
        for visita in visitas:
            visita.franja_id = None
            visita.franja_codigo = None
            visita.estado_franja = False
            if visita.latitud and visita.longitud:
                respuesta = VisitaServicio.ubicar_punto(franjas, visita.latitud, visita.longitud)
                if respuesta['encontrado']:
                    visita.franja_id = respuesta['franja']['id']
                    visita.franja_codigo = respuesta['franja']['codigo']
                    visita.estado_franja = True                
            visita.save()  
            cantidad += 1      
        return cantidad

    @staticmethod
    def ordenar(visitas: RutVisita):                  
        configuracion = GenConfiguracion.objects.filter(pk=1).values('rut_latitud', 'rut_longitud')[0]
        if not configuracion or configuracion['rut_latitud'] is None or configuracion['rut_longitud'] is None:
            return {'error': True, 'mensaje': 'Configuración de ruteo no encontrada o incompleta.'}
        
        latitud = float(configuracion['rut_latitud'])
        longitud = float(configuracion['rut_longitud'])

        punto_inicial = {'latitud': latitud, 'longitud': longitud}         
        matriz = VisitaServicio.construir_matriz_distancias(visitas, punto_inicial)                    
        manager = pywrapcp.RoutingIndexManager(len(matriz), 1, 0)
        routing = pywrapcp.RoutingModel(manager)
        
        def distancia_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return int(matriz[from_node][to_node] * 1000)
        
        transit_callback_index = routing.RegisterTransitCallback(distancia_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)                        
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        
        solution = routing.SolveWithParameters(search_parameters)            
        if not solution:
            return None

        index = routing.Start(0)
        orden = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node != 0:
                orden.append(node - 1)
            index = solution.Value(routing.NextVar(index))        
        decimal_6_places = Decimal('0.000001')  # Para redondear a 6 decimales
        
        for idx, visita_idx in enumerate(orden):                        
            '''visita_id = visitas[visita_idx]['id']            
            tiempo_servicio = Decimal(visitas[visita_idx]['tiempo_servicio']).quantize(decimal_6_places, rounding=ROUND_HALF_UP)
            distancia = matriz[0][visita_idx + 1] if idx == 0 else matriz[orden[idx - 1] + 1][visita_idx + 1]                    
            tiempo_trayecto = (Decimal(distancia) * Decimal('1.6')).quantize(decimal_6_places, rounding=ROUND_HALF_UP)            
            tiempo = (tiempo_servicio + tiempo_trayecto).quantize(decimal_6_places, rounding=ROUND_HALF_UP)            
            RutVisita.objects.filter(id=visita_id).update(orden=idx + 1, distancia=distancia, tiempo_trayecto=tiempo_trayecto, tiempo=tiempo)'''

            visita = visitas[visita_idx]
            distancia = Decimal(matriz[0][visita_idx + 1] if idx == 0 else matriz[orden[idx - 1] + 1][visita_idx + 1]).quantize(decimal_6_places)            
            tiempo_trayecto = (distancia * Decimal('1.6')).quantize(decimal_6_places)
            tiempo_servicio = Decimal(visita.tiempo_servicio).quantize(decimal_6_places)
            tiempo = (tiempo_servicio + tiempo_trayecto).quantize(decimal_6_places)
            
            visita.orden = idx + 1
            visita.distancia = Decimal(distancia)
            visita.tiempo_trayecto = Decimal(tiempo_trayecto)
            visita.tiempo = Decimal(tiempo)
            visita.save()
        return {'error': False}
    
    @staticmethod
    def importar_complemento(limite=100, guia_desde=None, guia_hasta=None, fecha_desde=None, fecha_hasta=None, pendiente_despacho=False, codigo_contacto=None, codigo_destino=None, codigo_zona=None, codigo_despacho=None, despacho_id=None):        
        parametros = {
            'limite': limite,
            'guia_desde': guia_desde,
            'guia_hasta': guia_hasta,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'pendiente_despacho': pendiente_despacho,
            'codigo_contacto': codigo_contacto,
            'codigo_destino' : codigo_destino,
            'codigo_zona': codigo_zona,
            'codigo_despacho': codigo_despacho
        }
        holmio = Holmio()
        respuesta = holmio.ruteo_pendiente(parametros)
        if respuesta['error'] == False:  
            configuracion = GenConfiguracion.objects.filter(pk=1).values('rut_decodificar_direcciones')[0]        
            google = Google()
            franjas = RutFranja.objects.all()
            cantidad = 0                                                    
            visitas_creadas = []
            guias = respuesta['guias']
            for guia in guias:                                                                        
                direccion_destinatario = VisitaServicio.limpiar_direccion(guia['direccionDestinatario'])                                               
                fecha = datetime.fromisoformat(guia['fechaIngreso'])  
                nombre_remitente = (guia['nombreRemitente'][:150] if guia['nombreRemitente'] is not None and guia['nombreRemitente'] != "" else None)
                nombre_destinatario = (guia['nombreDestinatario'][:150] if guia['nombreDestinatario'] is not None and guia['nombreDestinatario'] != "" else None)
                documentoCliente = (guia['documentoCliente'][:30] if guia['documentoCliente'] is not None and guia['documentoCliente'] != "" else None)
                telefono_destinatario = (guia['telefonoDestinatario'][:50] if guia['telefonoDestinatario'] is not None and guia['telefonoDestinatario'] != "" else None)
                data = {
                    'numero': guia['codigoGuiaPk'],
                    'fecha':fecha,
                    'documento': documentoCliente,
                    'remitente': nombre_remitente,
                    'destinatario': nombre_destinatario,
                    'destinatario_direccion': direccion_destinatario,
                    'ciudad': None,
                    'destinatario_telefono': telefono_destinatario,
                    'destinatario_correo': None,
                    'unidades': guia['unidades'] or 0,
                    'peso': guia['pesoReal'] or 0,
                    'volumen': guia['pesoVolumen'] or 0,
                    'cobro': guia['vrCobroEntrega'] or 0,
                    'latitud': None,
                    'longitud': None,
                    'estado_decodificado': False,
                    'tiempo_servicio': 3,
                    'estado_franja': False,
                    'franja': None,
                    'resultados': None,
                    'despacho': despacho_id,
                    'estado_despacho': despacho_id is not None
                } 
                if direccion_destinatario:                   
                    if configuracion['rut_decodificar_direcciones']:
                        direccion = CtnDireccion.objects.filter(direccion=direccion_destinatario).first()
                        if direccion:
                            data['estado_decodificado'] = True            
                            data['latitud'] = direccion.latitud                        
                            data['longitud'] = direccion.longitud
                            data['destinatario_direccion_formato'] = direccion.direccion_formato
                            data['resultados'] = direccion.resultados
                            if direccion.cantidad_resultados > 1:
                                data['estado_decodificado_alerta'] = True                                
                        else:                    
                            respuesta = google.decodificar_direccion(data['destinatario_direccion'])
                            if respuesta['error'] == False:   
                                data['estado_decodificado'] = True            
                                data['latitud'] = respuesta['latitud']
                                data['longitud'] = respuesta['longitud']
                                data['destinatario_direccion_formato'] = respuesta['direccion_formato']
                                data['resultados'] = respuesta['resultados']
                                if respuesta['cantidad_resultados'] > 1:
                                    data['estado_decodificado_alerta'] = True
                if data['estado_decodificado'] == True:
                    respuesta = VisitaServicio.ubicar_punto(franjas, data['latitud'], data['longitud'])
                    if respuesta['encontrado']:
                        data['franja'] = respuesta['franja']['id']
                        data['estado_franja'] = True
                    else:
                        data['estado_franja'] = False
                visitaSerializador = RutVisitaSerializador(data=data)
                if visitaSerializador.is_valid():
                    visita = visitaSerializador.save()
                    visitas_creadas.append(visita)
                    cantidad += 1                                                                                    
                else:
                    return {'error': True, 'mensaje': 'Errores de validación', 'validaciones': visitaSerializador.errors}
            return {'error': False, 'cantidad': cantidad, 'visitas_creadas': visitas_creadas}
        else:
            return {
                'error': True,
                'mensaje': f'Error en la conexion: {respuesta["mensaje"]}'
            }

    @staticmethod
    def entrega_complemento(visita: RutVisita, imagenes_b64, firmas_b64, datos_entrega): 
        holmio = Holmio()
        fecha_formateada = visita.fecha_entrega.strftime('%Y-%m-%d %H:%M')
        parametros = {
            'codigoGuia': visita.numero,
            'fechaEntrega': fecha_formateada,
            'usuario': 'ruteo'            
        }
        if imagenes_b64:
            parametros['imagenes'] = imagenes_b64
        if firmas_b64:
            parametros['firmarBase64'] = firmas_b64[0]['base64']
        if datos_entrega:
            parametros.update(datos_entrega)                    
        respuesta = holmio.entrega(parametros)
        if respuesta['error'] == False:
            visita.estado_entregado_complemento = True
            visita.save()