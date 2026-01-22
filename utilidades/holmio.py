from general.models.complemento import GenComplemento
from decouple import config
import requests
import json
from requests.auth import HTTPBasicAuth

class Holmio():

    def ruteo_pendiente(self, parametros):
        url = "/api/transporte/guia/ruteo/pendiente"        
        respuesta = self.consumirPost(parametros, url)        
        if respuesta['status'] == 200:
            datos = respuesta['datos']
            return {'error':False, 'guias': datos['guias']}
        else:
            return {'error':True, 'mensaje':f'Ocurrio un error con la clase: {respuesta["mensaje"]}'}
        
    def despacho_detalle(self, parametros):
        url = "/api/transporte/despacho/detalle"        
        respuesta = self.consumirPost(parametros, url)        
        if respuesta['status'] == 200:
            datos = respuesta['datos']
            return {'error':False, 'despacho': datos['despacho']}
        else:
            return {'error':True, 'mensaje':f'Ocurrio un error con la clase: {respuesta["mensaje"]}'}        

    def entrega(self, parametros):
        url = "/api/transporte/guia/entrega"        
        respuesta = self.consumirPost(parametros, url)        
        if respuesta['status'] == 200:
            datos = respuesta['datos']
            if datos['error'] == False:
                return {'error':False}
            else:
                error_codigo = datos.get('errorCodigo', None)
                if error_codigo == 1:
                    return {'error':False}
                else:
                    return {'error':True,'mensaje':f'Ocurrio un error con la entrega'}
        else:
            return {'error':True, 'mensaje':f'Ocurrio un error con la clase: {respuesta["mensaje"]}'}

    def novedad(self, parametros):
        url = "/api/transporte/novedad/nuevo"        
        respuesta = self.consumirPost(parametros, url)        
        if respuesta['status'] == 200:
            return {'error':False}
        else:
            return {'error':True, 'mensaje':f'Ocurrio un error con la clase: {respuesta["mensaje"]}'}

    def estado(self):
        url = "/api/seguridad/estado"        
        respuesta = self.consumirPost([], url)        
        if respuesta['status'] == 200:
            return {'error':False}
        else:
            return {'error':True, 'mensaje':f'Ocurrio un error con la clase: {respuesta["mensaje"]}'}

    def consumirPost(self, data, url):
        complemento = GenComplemento.objects.get(pk=1)
        if complemento:
            if isinstance(complemento.datos_json, list):
                    propiedades = {item['nombre']: item['valor'] for item in complemento.datos_json}
                    url_base = propiedades.get('url')
                    usuario = propiedades.get('usuario')
                    clave = propiedades.get('clave')                
                    if url_base and usuario and clave:  
                        url_completa = url_base + url    
                        json_data = json.dumps(data)
                        headers = {'Content-Type': 'application/json'}
                        response = requests.post(
                            url_completa,
                            data=json_data,
                            headers=headers,
                            auth=HTTPBasicAuth(usuario, clave)
                        )                     
                        status = response.status_code
                        if status == 200:
                            resp = response.json()
                            return {'status': status, 'datos': resp}
                        if status == 401:
                            return {'status': status, 'mensaje':"Error de autorizacion"}  
                        else:                                                                     
                            return {'status': status, 'mensaje':"Error no especificado"}                                            
                    else:
                        return {'status': 500, 'mensaje': 'Debe configurar los datos del complemento'}    
                
            else:
                return {'status': 500, 'mensaje': 'El complemento no tiene json valido'}
        else:
            return {'status': 500, 'mensaje': 'El complemento no existe'}




