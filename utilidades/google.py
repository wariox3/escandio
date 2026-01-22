from contenedor.models import CtnDireccion
from ruteo.models.visita import RutVisita
from decouple import config
from django.utils.timezone import now
import requests
import googlemaps
from general.models.configuracion import GenConfiguracion

class Google():

    def __init__(self):
        api_key = config('GOOGLE_MAPS_API_KEY')
        self.gmaps = googlemaps.Client(key=api_key)

    def decodificar_direccion(self, direccion_parametro):                                
        api_key = config('GOOGLE_MAPS_API_KEY')
        base_url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            #"address": f"{direccion_parametro}, COLOMBIA",
            "address": direccion_parametro,
            "key": api_key,
            "components": "country:CO"
        }
        response = requests.get(base_url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'OK':                
                resultados = data['results']
                cantidad_resultados = len(resultados)
                location = resultados[0]['geometry']['location']
                direccion_formato = resultados[0]['formatted_address']
                direccion = CtnDireccion()
                direccion.fecha = now()
                direccion.direccion = direccion_parametro
                direccion.direccion_formato = direccion_formato
                direccion.latitud = location['lat']
                direccion.longitud = location['lng']
                direccion.cantidad_resultados = cantidad_resultados
                direccion.resultados = resultados
                direccion.save()
                return {
                    "error": False,
                    "direccion_formato": direccion_formato,
                    "latitud": location['lat'],
                    "longitud": location['lng'],
                    "cantidad_resultados": cantidad_resultados,
                    "resultados": resultados
                }
            else:
                return {"error": True, "mensaje": data.get('error_message', 'Error desconocido de google')}
        else:
            return {"error": True, "mensaje": "Estatus code de google diferente a 200"}

    def calcular_ruta(self, visitas):      
                                      
        api_key = config('GOOGLE_MAPS_API_KEY')
        base_url = "https://maps.googleapis.com/maps/api/directions/json"
        waypoints = "|".join([f"{visita['latitud']},{visita['longitud']}" for visita in visitas])        
        cantidad_visitas = len(visitas)
        params = {
            "origin": f"6.197023,-75.585760",
            "destination": f"6.197023,-75.585760",
            "waypoints": f"optimize:true|{waypoints}",
            "key": api_key
        }
        response = requests.get(base_url, params=params)                
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'OK':                                
                ruta = data["routes"][0]                
                waypoint_order = ruta["waypoint_order"]
                entregas_ordenadas = [visitas[i] for i in waypoint_order]
                
                '''for i, leg in enumerate(ruta["legs"]):
                    visita_actual = entregas_ordenadas[i]
                    distancia = leg["distance"]["value"]  # En metros
                    tiempo = leg["duration"]["value"]  # En segundos

                    visita_actualizar = RutVisita.objects.get(id=visita_actual["id"])
                    visita_actualizar.orden = i + 1
                    #visita_actualizar.distancia_proxima = distancia
                    #visita_actualizar.tiempo_proxima = tiempo
                    visita_actualizar.save()'''

                return {
                    "error": False,
                    "ruta": ruta, 
                    "ruta_puntos": ruta["overview_polyline"]["points"],
                    "orden_entregas": entregas_ordenadas,
                }
            else:
                return {"error": True, "mensaje": data.get('error_message', 'Error desconocido de google')}
        else:
            return {"error": True, "mensaje": "Estatus code de google diferente a 200"}
    
    def direcciones(self, visitas):
        api_key = config('GOOGLE_MAPS_API_KEY')

        configuracion = GenConfiguracion.objects.first()
        origen = f"{configuracion.rut_latitud},{configuracion.rut_longitud}"
        
        visitas_limitadas = visitas[:25]
        
        visitas_ordenadas = sorted(visitas_limitadas, key=lambda x: x.get('orden', 0))
        
        # 2. Preparar waypoints (excluyendo el último punto que será el destino)
        destino = visitas_ordenadas[-1]
        waypoints = [
            f"{w['latitud']},{w['longitud']}" 
            for w in visitas_ordenadas[:-1]
        ]
        
        # 3. Llamar a la API de Directions
        params = {
            "origin": origen,
            "destination": f"{destino['latitud']},{destino['longitud']}",
            "waypoints": "|".join(waypoints),
            "optimizeWaypoints": "false",
            "mode": "driving",
            "key": api_key,
        }
    

        # 5. Llamar a la API de Google Maps
        try:
            response = requests.get(
                "https://maps.googleapis.com/maps/api/directions/json",
                params=params,
                timeout=15
            )
            data = response.json()

            if data['status'] != 'OK':
                return {
                    "error": True,
                    "mensaje": data.get('error_message', 'Error en Google Maps'),
                    "status": data['status']
                }

            # 4. Extraer la geometría detallada de cada tramo (leg)
            puntos_ruta = []
            for leg in data['routes'][0]['legs']:
                for step in leg['steps']:
                    # Decodificar el polyline de cada segmento
                    puntos = self._decode_polyline(step['polyline']['points'])
                    puntos_ruta.extend(puntos)
            
            return {
                "error": False,
                "puntos_detallados": puntos_ruta,  # Coordenadas que siguen calles
                "ruta_simplificada": data['routes'][0]['overview_polyline']['points'],
                "distancia": data['routes'][0]['legs'][0]['distance']['text'],
                "duracion": data['routes'][0]['legs'][0]['duration']['text'],
                "data": data
            }

        except Exception as e:
            return {"error": True, "mensaje": str(e)}

    def matriz_distancia(self, visitas_ubicaciones):
        api_key = config('GOOGLE_MAPS_API_KEY')                                                        
        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            "origins": '|'.join(f"{lat},{lng}" for lat, lng in visitas_ubicaciones),
            "destinations": '|'.join(f"{lat},{lng}" for lat, lng in visitas_ubicaciones),
            "mode": "driving",
            "key": api_key
        }
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()        
            if data['status'] == 'OK':  
                distances = [
                    [element['distance']['value'] for element in row['elements']]
                    for row in data['rows']
                ]                   
                durations = [
                    [element['duration']['value'] for element in row['elements']]
                    for row in data['rows']
                ]
                return {'error':False, 'distancias':distances, 'duraciones': durations}                                 
            else:
               return {"error": True, "mensaje": data.get('error_message', 'Error desconocido de google')}
        else:
           return {"error": True, "mensaje": "Estatus code de google diferente a 200"}  
      
    def _decode_polyline(self, polyline_str):
        """
        Decodifica un string polyline de Google Maps en una lista de coordenadas [lat, lng].
        Basado en el algoritmo oficial de Google.
        """
        index, lat, lng = 0, 0, 0
        coordinates = []
        changes = {'latitude': 0, 'longitude': 0}
        
        # Los caracteres ASCII se decodifican en valores decimal
        while index < len(polyline_str):
            # Decodificar latitud
            shift, result = 0, 0
            while True:
                byte = ord(polyline_str[index]) - 63
                index += 1
                result |= (byte & 0x1f) << shift
                shift += 5
                if byte < 0x20:
                    break
            changes['latitude'] = ~(result >> 1) if (result & 1) else (result >> 1)
            
            # Decodificar longitud
            shift, result = 0, 0
            while True:
                byte = ord(polyline_str[index]) - 63
                index += 1
                result |= (byte & 0x1f) << shift
                shift += 5
                if byte < 0x20:
                    break
            changes['longitude'] = ~(result >> 1) if (result & 1) else (result >> 1)
            
            lat += changes['latitude']
            lng += changes['longitude']
            coordinates.append([lat / 100000.0, lng / 100000.0])
        
        return coordinates