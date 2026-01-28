from contenedor.models import CtnDireccion
from ruteo.servicios.visita import VisitaServicio
from utilidades.google import Google

class DireccionServicio():

    @staticmethod
    def decodificar(direccion_decodificar):        
        if direccion_decodificar:          
            direccion_limpia = VisitaServicio.limpiar_direccion(direccion_decodificar)                                  
            direccion = CtnDireccion.objects.filter(direccion=direccion_limpia).first()
            if direccion:
                data = {
                    'latitud': direccion.latitud,
                    'longitud': direccion.longitud,
                    'direccion_original': direccion_limpia,
                    'direccion_formato': direccion.direccion_formato,
                    'cantidad_resultados': direccion.cantidad_resultados,
                    'resultados': direccion.resultados,                    
                }
                return{'error': False, 'datos': data}                         
            else:
                google = Google()
                respuesta = google.decodificar_direccion(direccion_limpia)                
                if respuesta['error'] == False:  
                    data = {
                        'latitud': respuesta['latitud'],
                        'longitud': respuesta['longitud'],
                        'direccion_original': direccion_limpia,
                        'direccion_formato': respuesta['direccion_formato'],
                        'cantidad_resultados': respuesta['cantidad_resultados'],
                        'resultados': respuesta['resultados'],                        
                    }                     
                    return{'error': False, 'datos': data}
                else:
                    return{'error': True, 'mensaje': 'No se pudo decodificar la direccion'}                         
        else:
            return {'error':True, 'mensaje': 'Faltan parametros'}              