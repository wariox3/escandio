import requests
import json

class Zinc():

    def log_correo(self, operador, documento_id):
        url = "/api/externo/correo/v2"
        datos = {
            "operador" : operador,
            "codigoDocumento" : documento_id
        }
        respuesta = self.consumirPost(datos, url)
        if respuesta['status'] == 200:
            datos = respuesta['datos']
            return {'error': False, 'correos': datos['correos']}
        else:
            return {'error':True, 'mensaje':'Ocurrio un error en el servicio zinc'}

    def log_evento(self, operador, documento_id):
        url = "/api/externo/evento/v3"
        datos = {
            "operador" : operador,
            "codigoDocumento" : documento_id
        }
        respuesta = self.consumirPost(datos, url)
        if respuesta['status'] == 200:
            datos = respuesta['datos']
            return {'error': False, 'eventos': datos['eventos']}
        else:
            return {'error':True, 'mensaje':'Ocurrio un error en el servicio zinc'}

    def log_envio(self, operador, documento_id):
        url = "/api/externo/log_envio"
        datos = {
            "operador" : operador,
            "codigoDocumento" : documento_id
        }
        respuesta = self.consumirPost(datos, url)
        if respuesta['status'] == 200:
            datos = respuesta['datos']
            return {'error': False, 'log': datos['log']}
        else:
            return {'error':True, 'mensaje':'Ocurrio un error en el servicio zinc'}           

    def correo(self, correo, asunto, contenido, aplicacion='reddoc', archivos = []):
        url = "/api/correo/itrio"
        datos = {
            "correo" : correo,
            "asunto" : asunto,
            "contenido": contenido,
            "aplicacion":aplicacion,
            "archivos": archivos
        }
        respuesta = self.consumirPost(datos, url)
        if respuesta['status'] == 200:
            return {'error': False}
        else:
            return {'error':True, 'mensaje':'Ocurrio un error en el servicio zinc'}

    def decodificar_direccion(self, datos):
        url = "/api/direccion/nuevo"
        respuesta = self.consumirPost(datos, url)
        if respuesta['status'] == 200:
            datos = respuesta['datos']
            return {'error': False, 'datos': datos}
        else:
            return {'error':True, 'mensaje':'Ocurrio un error en el servicio zinc'}

    def consumirPost(self, data, url):
        url = "http://zinc.semantica.com.co" + url        
        json_data = json.dumps(data)
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, data=json_data, headers=headers)
        resp = response.json()
        return {'status': response.status_code, 'datos': resp}


