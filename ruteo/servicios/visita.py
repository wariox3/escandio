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
from datetime import datetime, time
from shapely.geometry import Point, Polygon
from math import radians, cos, sin, asin, sqrt, atan2
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from decimal import Decimal, ROUND_HALF_UP
import numpy as np
import re
import logging

logger = logging.getLogger(__name__)

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
        # Sin coordenadas del punto no se puede ubicar.
        if latitud is None or longitud is None:
            return {'encontrado': False}
        punto = Point(longitud, latitud)
        for franja in franjas:
            coords = franja.coordenadas
            # Una franja creada pero NO dibujada tiene coordenadas=None (o una
            # lista con menos de 3 puntos / malformada). Antes esto reventaba:
            # `for coord in None` -> TypeError -> 500 en TODO lo que ubica
            # (editar direccion, importar, rutear). Se ignora la franja invalida.
            if not isinstance(coords, list) or len(coords) < 3:
                continue
            try:
                coordenadas = [(coord['lng'], coord['lat']) for coord in coords]
                poligono = Polygon(coordenadas)
                if poligono.contains(punto):
                    return {'encontrado': True, 'franja': {'id': franja.id, 'codigo': franja.codigo}}
            except (KeyError, TypeError, ValueError):
                # Coordenadas malformadas (falta lng/lat, tipos raros): se ignora
                # la franja en vez de tumbar toda la operacion.
                continue
        return {'encontrado': False}

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
        # .first() en vez de [0]: si no existe la fila de configuracion, [0]
        # lanzaba IndexError (500) ANTES de que el guard de abajo pudiera
        # devolver el error 13 controlado.
        configuracion = GenConfiguracion.objects.filter(pk=1).values('rut_latitud', 'rut_longitud', 'rut_hora_inicio', 'rut_estrategia_ruteo').first()
        if not configuracion or configuracion['rut_latitud'] is None or configuracion['rut_longitud'] is None:
            return {'error': True, 'mensaje': 'Configuración de ruteo no encontrada o incompleta, verifique la dirección de origen en configuración', "codigo": 13}

        from django.utils import timezone
        visitas = list(visitas)

        # Pre-filtro: rechazar visitas con cita obligatoria ya vencida en vez
        # de abortar todo el rutear. Una visita "mala" no debe romper la pila.
        # Las rechazadas se reportan al final junto con las que falle el
        # algoritmo de asignacion (capacidad/franja/etc).
        ahora = timezone.localtime(timezone.now())
        rechazos: dict = {}
        rechazos_ids: list = []
        visitas_validas = []
        for v in visitas:
            if v.cita_inicio and v.cita_fin:
                tipo = getattr(v, 'cita_tipo', 'obligatoria') or 'obligatoria'
                if tipo == 'obligatoria' and v.cita_fin < ahora:
                    ref = v.numero or v.documento or f'#{v.id}'
                    rechazos[ref] = (
                        f'Cita obligatoria ya pasó '
                        f'({v.cita_inicio.strftime("%Y-%m-%d %H:%M")}-'
                        f'{v.cita_fin.strftime("%H:%M")})'
                    )
                    rechazos_ids.append(v.id)
                    continue
            visitas_validas.append(v)

        if not visitas_validas:
            return {
                'error': False,
                'rechazos': rechazos,
                'rechazos_ids': rechazos_ids,
                'mensaje': 'Todas las visitas fueron rechazadas por cita vencida',
            }

        tiene_citas = any(v.cita_inicio is not None for v in visitas_validas)
        if tiene_citas:
            resultado = VisitaServicio._ordenar_con_ventanas(visitas_validas, configuracion)
            if resultado and resultado.get('error'):
                tiene_obligatorias = any(
                    getattr(v, 'cita_tipo', 'obligatoria') == 'obligatoria'
                    for v in visitas_validas if v.cita_inicio is not None
                )
                if tiene_obligatorias:
                    resultado['rechazos'] = {**resultado.get('rechazos', {}), **rechazos}
                    resultado['rechazos_ids'] = [*resultado.get('rechazos_ids', []), *rechazos_ids]
                    return resultado
                resultado = VisitaServicio._ordenar_distancia(visitas_validas, configuracion)
        else:
            resultado = VisitaServicio._ordenar_distancia(visitas_validas, configuracion)

        if resultado is None:
            resultado = {}
        resultado['rechazos'] = {**resultado.get('rechazos', {}), **rechazos}
        resultado['rechazos_ids'] = [*resultado.get('rechazos_ids', []), *rechazos_ids]
        return resultado

    @staticmethod
    def _ordenar_distancia(visitas: RutVisita, configuracion):
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
            return {'error': True, 'mensaje': 'No se encontró una solución factible para ordenar las visitas.', 'codigo': 14}

        index = routing.Start(0)
        orden = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node != 0:
                orden.append(node - 1)
            index = solution.Value(routing.NextVar(index))
        decimal_6_places = Decimal('0.000001')

        for idx, visita_idx in enumerate(orden):
            visita = visitas[visita_idx]
            distancia = Decimal(matriz[0][visita_idx + 1] if idx == 0 else matriz[orden[idx - 1] + 1][visita_idx + 1]).quantize(decimal_6_places)
            tiempo_trayecto = (distancia * Decimal('1.6')).quantize(decimal_6_places)
            tiempo_servicio = Decimal(visita.tiempo_servicio).quantize(decimal_6_places)
            tiempo = (tiempo_servicio + tiempo_trayecto).quantize(decimal_6_places)

            visita.orden = idx + 1
            visita.distancia = Decimal(distancia)
            visita.tiempo_trayecto = Decimal(tiempo_trayecto)
            visita.tiempo = Decimal(tiempo)
            # update_fields: el solver tarda segundos y un save() completo
            # pisaría una entrega registrada por el conductor en ese intervalo.
            visita.save(update_fields=['orden', 'distancia', 'tiempo_trayecto', 'tiempo'])
        return {'error': False}

    @staticmethod
    def _ordenar_con_ventanas(visitas: RutVisita, configuracion):
        from django.utils import timezone

        latitud = float(configuracion['rut_latitud'])
        longitud = float(configuracion['rut_longitud'])

        # Hora de salida del vehículo: la mayor entre hora configurada y hora actual
        hora_inicio = configuracion.get('rut_hora_inicio')
        ahora = timezone.localtime(timezone.now())
        hoy = ahora.date()
        if not hora_inicio:
            hora_inicio = time(7, 0)
        hora_salida_naive = datetime.combine(hoy, hora_inicio)
        hora_salida = timezone.make_aware(hora_salida_naive) if timezone.is_naive(hora_salida_naive) else hora_salida_naive
        if ahora > hora_salida:
            hora_salida = ahora

        punto_inicial = {'latitud': latitud, 'longitud': longitud}
        matriz = VisitaServicio.construir_matriz_distancias(visitas, punto_inicial)

        # Convertir matriz de distancias (km) a matriz de tiempo (minutos): km * 1.6 min/km
        n = len(matriz)
        time_matrix = [[0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                time_matrix[i][j] = int(matriz[i][j] * 1.6)

        # Horizonte de jornada en minutos (14 horas desde hora de salida)
        horizonte = 14 * 60

        # Construir ventanas horarias y tipos por nodo (minutos relativos a hora_salida)
        # Nodo 0 = depósito, nodos 1..n = visitas
        ventanas = [(0, 0)]  # Depósito: salida inmediata
        tipos_cita = [None]  # depósito no tiene tipo
        for v in visitas:
            if v.cita_inicio and v.cita_fin:
                tw_inicio = int((v.cita_inicio - hora_salida).total_seconds() / 60)
                tw_fin = int((v.cita_fin - hora_salida).total_seconds() / 60)

                tipo = getattr(v, 'cita_tipo', 'obligatoria') or 'obligatoria'

                # Validación previa para citas obligatorias
                if tipo == 'obligatoria':
                    # Identificador legible: numero si existe, sino documento, sino id.
                    ref = v.numero or v.documento or f'#{v.id}'
                    if tw_fin < 0:
                        return {
                            'error': True,
                            'mensaje': (
                                f'La cita obligatoria de la visita {ref} ya pasó '
                                f'({v.cita_inicio.strftime("%Y-%m-%d %H:%M")}-'
                                f'{v.cita_fin.strftime("%H:%M")}). '
                                f'Cambia la cita o pásala a "preferente".'
                            ),
                            'codigo': 14,
                            'visita_id': v.id,
                        }
                    # Verificar si es físicamente posible llegar desde el origen
                    tiempo_minimo_desde_origen = time_matrix[0][len(ventanas)]
                    if tiempo_minimo_desde_origen > tw_fin:
                        return {
                            'error': True,
                            'mensaje': (
                                f'Imposible cumplir la cita obligatoria de la visita {ref}. '
                                f'Cita: {v.cita_inicio.strftime("%H:%M")}-{v.cita_fin.strftime("%H:%M")}. '
                                f'Tiempo mínimo de traslado: {tiempo_minimo_desde_origen} min. '
                                f'Tiempo disponible: {max(0, tw_fin)} min.'
                            ),
                            'codigo': 14,
                            'visita_id': v.id,
                        }

                tw_inicio = max(0, tw_inicio)
                tw_fin = min(horizonte, tw_fin)

                # Para preferentes con ventana ya pasada, abrir ventana completa
                if tipo == 'preferente' and tw_fin <= 0:
                    ventanas.append((0, horizonte))
                    tipos_cita.append('preferente')
                else:
                    ventanas.append((tw_inicio, tw_fin))
                    tipos_cita.append(tipo)
            else:
                ventanas.append((0, horizonte))
                tipos_cita.append(None)

        logger.info(f'Ventanas horarias: hora_salida={hora_salida}, horizonte={horizonte}min')
        for i, v in enumerate(visitas):
            logger.info(f'  Visita {v.numero} ({v.destinatario[:20]}): ventana={ventanas[i+1]}, tipo={tipos_cita[i+1]}')

        manager = pywrapcp.RoutingIndexManager(n, 1, 0)
        routing = pywrapcp.RoutingModel(manager)

        # Callback de tiempo (travel_time + service_time) — usado como costo y dimensión
        def tiempo_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            travel_time = time_matrix[from_node][to_node]
            if to_node > 0:
                service_time = int(float(visitas[to_node - 1].tiempo_servicio))
            else:
                service_time = 0
            return travel_time + service_time

        time_callback_index = routing.RegisterTransitCallback(tiempo_callback)

        # Callback de distancia
        def distancia_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return int(matriz[from_node][to_node] * 1000)

        distancia_callback_index = routing.RegisterTransitCallback(distancia_callback)

        # Seleccionar costo según estrategia
        estrategia = configuracion.get('rut_estrategia_ruteo', 'balanceado')
        if estrategia == 'distancia':
            routing.SetArcCostEvaluatorOfAllVehicles(distancia_callback_index)
        else:
            routing.SetArcCostEvaluatorOfAllVehicles(time_callback_index)

        # Dimensión de tiempo para aplicar ventanas horarias
        routing.AddDimension(
            time_callback_index,
            horizonte,   # slack máximo (tiempo de espera permitido)
            horizonte,   # tiempo máximo acumulado por vehículo
            True,        # forzar inicio en 0 (salida inmediata)
            'Time'
        )
        time_dimension = routing.GetDimensionOrDie('Time')

        # Penalización para citas preferentes (1000 por minuto fuera de ventana)
        PENALIZACION_PREFERENTE = 1000

        # Aplicar ventanas horarias según tipo
        for i in range(n):
            index = manager.NodeToIndex(i)
            tw_inicio, tw_fin = ventanas[i]
            tipo = tipos_cita[i]

            if tipo == 'obligatoria':
                # Hard constraint: DEBE llegar dentro de la ventana
                time_dimension.CumulVar(index).SetRange(tw_inicio, tw_fin)
            elif tipo == 'preferente':
                # Soft constraint: intenta llegar pero puede violar con penalización
                time_dimension.CumulVar(index).SetRange(0, horizonte)
                time_dimension.SetCumulVarSoftLowerBound(index, tw_inicio, PENALIZACION_PREFERENTE)
                time_dimension.SetCumulVarSoftUpperBound(index, tw_fin, PENALIZACION_PREFERENTE)
            else:
                # Sin cita: ventana abierta
                time_dimension.CumulVar(index).SetRange(tw_inicio, tw_fin)

        # Coeficiente de span según estrategia
        if estrategia == 'distancia':
            time_dimension.SetGlobalSpanCostCoefficient(0)
        elif estrategia == 'tiempo':
            time_dimension.SetGlobalSpanCostCoefficient(10)
        else:  # balanceado
            time_dimension.SetGlobalSpanCostCoefficient(3)

        # Estrategia de búsqueda
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        search_parameters.time_limit.seconds = 5

        solution = routing.SolveWithParameters(search_parameters)
        if not solution:
            return {
                'error': True,
                'mensaje': 'No se encontró una solución factible. Verifique que las ventanas horarias (citas obligatorias) sean compatibles entre sí.',
                'codigo': 14
            }

        index = routing.Start(0)
        orden = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node != 0:
                orden.append(node - 1)
            index = solution.Value(routing.NextVar(index))
        decimal_6_places = Decimal('0.000001')

        for idx, visita_idx in enumerate(orden):
            visita = visitas[visita_idx]
            distancia = Decimal(matriz[0][visita_idx + 1] if idx == 0 else matriz[orden[idx - 1] + 1][visita_idx + 1]).quantize(decimal_6_places)
            tiempo_trayecto = (distancia * Decimal('1.6')).quantize(decimal_6_places)
            tiempo_servicio = Decimal(visita.tiempo_servicio).quantize(decimal_6_places)
            tiempo = (tiempo_servicio + tiempo_trayecto).quantize(decimal_6_places)

            visita.orden = idx + 1
            visita.distancia = Decimal(distancia)
            visita.tiempo_trayecto = Decimal(tiempo_trayecto)
            visita.tiempo = Decimal(tiempo)
            # update_fields: el solver tarda segundos y un save() completo
            # pisaría una entrega registrada por el conductor en ese intervalo.
            visita.save(update_fields=['orden', 'distancia', 'tiempo_trayecto', 'tiempo'])
        return {
            'error': False,
            'debug': {
                'hora_salida': str(hora_salida),
                'ventanas': {str(visitas[i].numero): {'ventana': ventanas[i+1], 'tipo': tipos_cita[i+1]} for i in range(len(visitas))},
                'orden_resultado': [visitas[i].numero for i in orden],
            }
        }

    @staticmethod
    def importar_complemento(limite=100, guia_desde=None, guia_hasta=None, fecha_desde=None, fecha_hasta=None, pendiente_despacho=False, codigo_contacto=None, codigo_destino=None, codigo_zona=None, codigo_despacho=None, despacho_id=None, franja_ids=None, zona_destino=None):
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
            'codigo_despacho': codigo_despacho,
            # Filtro de ZONA de Semantica (en el origen): elegir una zona trae
            # todas las guias de esa zona. Si el nombre real del parametro en
            # Semantica resulta distinto, cambiar SOLO esta clave.
            'zona_destino': zona_destino,
        }
        holmio = Holmio()
        google = Google()
        franjas = RutFranja.objects.all()
        franja_ids = [int(f) for f in franja_ids] if franja_ids else None
        cantidad = 0
        descartadas = 0
        sin_ubicar = 0
        visitas_creadas = []
        # Con filtro de zonas las guías descartadas siguen pendientes en el
        # complemento y volverían a ocupar la ventana `limite` en cada intento
        # (nunca se llegaría a las guías en zona más allá de la ventana). Se
        # avanza el cursor guia_desde por lotes —asume que el complemento
        # responde ordenado por número de guía— hasta completar `limite`
        # guías importadas o agotar las pendientes.
        max_lotes = 10 if franja_ids is not None else 1
        lote = 0
        while lote < max_lotes:
            lote += 1
            respuesta = holmio.ruteo_pendiente(parametros)
            if respuesta['error'] != False:
                if lote == 1:
                    return {
                        'error': True,
                        'mensaje': f'Error en la conexion: {respuesta["mensaje"]}'
                    }
                break
            guias = respuesta['guias']
            if not guias:
                break
            # LOG TEMPORAL (QUITAR tras diagnosticar): descubrir si la guia de
            # Semantica trae su "zona" y con que nombre de campo, para cablear el
            # filtro por zona de Semantica en el import. Solo la 1a guia del 1er
            # lote y SOLO nombres de campo (no valores) para no volcar PII; ademas
            # los pares cuyo nombre menciona "zona" (ahi el valor es el codigo).
            if lote == 1 and isinstance(guias[0], dict):
                _g = guias[0]
                _zona = {k: v for k, v in _g.items() if 'zona' in k.lower()}
                # warning (no info): sin config de LOGGING el umbral efectivo es
                # WARNING, un info no se veria en los logs del server.
                logger.warning(
                    '[DEBUG-ZONA] claves_guia=%s | campos_zona=%s',
                    sorted(_g.keys()), _zona,
                )
            for guia in guias:
                if cantidad >= limite:
                    break
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
                    'estado_despacho': despacho_id is not None,
                    'cita_inicio': guia.get('citaInicio'),
                    'cita_fin': guia.get('citaFin'),
                } 
                if direccion_destinatario:
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
                        respuesta_google = google.decodificar_direccion(data['destinatario_direccion'])
                        if respuesta_google['error'] == False:
                            data['estado_decodificado'] = True
                            data['latitud'] = respuesta_google['latitud']
                            data['longitud'] = respuesta_google['longitud']
                            data['destinatario_direccion_formato'] = respuesta_google['direccion_formato']
                            data['resultados'] = respuesta_google['resultados']
                            if respuesta_google['cantidad_resultados'] > 1:
                                data['estado_decodificado_alerta'] = True
                if data['estado_decodificado'] == True:
                    respuesta_franja = VisitaServicio.ubicar_punto(franjas, data['latitud'], data['longitud'])
                    if respuesta_franja['encontrado']:
                        data['franja'] = respuesta_franja['franja']['id']
                        data['estado_franja'] = True
                    else:
                        data['estado_franja'] = False
                if franja_ids is not None:
                    if not data['estado_decodificado']:
                        # Sin coordenadas no hay forma de saber la zona: se
                        # importa para corrección manual en vez de descartarla.
                        sin_ubicar += 1
                    elif data['franja'] not in franja_ids:
                        # Filtro local por zona: la guía queda pendiente en el
                        # complemento y puede importarse luego con otra zona.
                        descartadas += 1
                        continue
                visitaSerializador = RutVisitaSerializador(data=data)
                if visitaSerializador.is_valid():
                    visita = visitaSerializador.save()
                    visitas_creadas.append(visita)
                    cantidad += 1                                                                                    
                else:
                    return {'error': True, 'mensaje': 'Errores de validación', 'validaciones': visitaSerializador.errors}
            if cantidad >= limite:
                break
            if len(guias) < limite:
                # El complemento devolvió menos que la ventana: no hay más pendientes.
                break
            try:
                maximo_numero = max(int(g['codigoGuiaPk']) for g in guias)
            except (TypeError, ValueError):
                # Números de guía no numéricos: no se puede avanzar el cursor.
                break
            nuevo_desde = maximo_numero + 1
            guia_hasta_actual = parametros.get('guia_hasta')
            if guia_hasta_actual and nuevo_desde > int(guia_hasta_actual):
                break
            parametros['guia_desde'] = nuevo_desde
        return {'error': False, 'cantidad': cantidad, 'descartadas': descartadas, 'sin_ubicar': sin_ubicar, 'visitas_creadas': visitas_creadas}

    @staticmethod
    def entrega_complemento(visita: RutVisita, imagenes_b64, firmas_b64, datos_entrega):
        if visita.fecha_entrega is None:
            VisitaServicio._sumar_intento_complemento(visita)
            return {'error': True, 'mensaje': 'La visita no tiene fecha de entrega'}
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
            visita.save(update_fields=['estado_entregado_complemento'])
            return {'error': False}
        if respuesta.get('rechazo'):
            VisitaServicio._sumar_intento_complemento(visita)
        return respuesta

    @staticmethod
    def _sumar_intento_complemento(visita: RutVisita):
        visita.entrega_complemento_intentos += 1
        visita.save(update_fields=['entrega_complemento_intentos'])