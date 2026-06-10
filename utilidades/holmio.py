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
            if datos.get('error') == False:
                return {'error':False}
            error_codigo = datos.get('errorCodigo', None)
            if error_codigo == 1:
                return {'error':False}
            detalle = datos.get('errorMensaje') or datos.get('mensaje') or 'sin detalle'
            return {'error':True, 'mensaje':f'Ocurrio un error con la entrega: {detalle}'}
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
        try:
            complemento = GenComplemento.objects.get(pk=1)
        except GenComplemento.DoesNotExist:
            return {'status': 500, 'mensaje': 'El complemento no existe'}
        if not isinstance(complemento.datos_json, list):
            return {'status': 500, 'mensaje': 'El complemento no tiene json valido'}
        propiedades = {item['nombre']: item['valor'] for item in complemento.datos_json}
        url_base = propiedades.get('url')
        usuario = propiedades.get('usuario')
        clave = propiedades.get('clave')
        if not (url_base and usuario and clave):
            return {'status': 500, 'mensaje': 'Debe configurar los datos del complemento'}
        url_completa = url_base + url
        json_data = json.dumps(data)
        headers = {'Content-Type': 'application/json'}
        try:
            response = requests.post(
                url_completa,
                data=json_data,
                headers=headers,
                auth=HTTPBasicAuth(usuario, clave),
                timeout=30
            )
        except requests.exceptions.RequestException as e:
            return {'status': 500, 'mensaje': f'No se pudo conectar con el complemento: {e}'}
        status = response.status_code
        if status == 200:
            try:
                resp = response.json()
            except ValueError:
                return {'status': 500, 'mensaje': 'El complemento respondio un contenido que no es json'}
            return {'status': status, 'datos': resp}
        if status == 401:
            return {'status': status, 'mensaje': "Error de autorizacion"}
        return {'status': status, 'mensaje': "Error no especificado"}




