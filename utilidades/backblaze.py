from b2sdk.v2 import InMemoryAccountInfo, B2Api, UploadSourceBytes
from decouple import config
from datetime import datetime
import base64
import uuid

class Backblaze():

    def __init__(self):   
        app_key_id = config('B2_APP_KEY_ID')
        app_key = config('B2_APP_KEY')     
        self.info = InMemoryAccountInfo()
        self.b2_api = B2Api(self.info)
        self.b2_api.authorize_account("production", app_key_id, app_key)

    def subir(self, base64_data, tenant, nombre_archivo):
        bucket_nombre = config('B2_BUCKET_NAME')
        bucket = self.b2_api.get_bucket_by_name(bucket_nombre)
        if bucket is None:
            raise ValueError(f"El bucket '{bucket_nombre}' no existe.")         
        file_data = base64.b64decode(base64_data)                
        uuid_referencia = uuid.uuid4()
        nombre_archivo = f"{tenant}/{uuid_referencia}_{nombre_archivo}"
        response = bucket.upload_bytes(
            file_data,
            nombre_archivo
        )                
        return response.id_, response.size, response.content_type, uuid_referencia   
    
    def subir_data(self, file_data, tenant, nombre_archivo):
        bucket_nombre = config('B2_BUCKET_NAME')
        bucket = self.b2_api.get_bucket_by_name(bucket_nombre)
        if bucket is None:
            raise ValueError(f"El bucket '{bucket_nombre}' no existe.")                               
        uuid_referencia = uuid.uuid4()
        anio_mes_actual = datetime.now().strftime("%Y/%m")        
        url = f"{tenant}/{anio_mes_actual}/{uuid_referencia}_{nombre_archivo}"        
        response = bucket.upload_bytes(file_data, url)                
        return response.id_, response.size, response.content_type, uuid_referencia, url

    def descargar(self, archivo_id):
        bucket_nombre = config('B2_BUCKET_NAME')
        bucket = self.b2_api.get_bucket_by_name(bucket_nombre)
        if bucket is None:
            raise ValueError(f"El bucket '{bucket_nombre}' no existe.")         
                        
        downloaded_file = bucket.download_file_by_id(archivo_id)  
        return downloaded_file.response
    
    def descargar_bytes(self, archivo_id):
        bucket_nombre = config('B2_BUCKET_NAME')
        bucket = self.b2_api.get_bucket_by_name(bucket_nombre)
        if bucket is None:
            raise ValueError(f"El bucket '{bucket_nombre}' no existe.")         
                        
        downloaded_file = bucket.download_file_by_id(archivo_id)  
        return downloaded_file.response.content    
    
    def eliminar(self, archivo_id):
        try:
            file_info = self.b2_api.get_file_info(archivo_id)
            file_name = file_info.file_name
            self.b2_api.delete_file_version(archivo_id, file_name)
            return True
        except Exception as e:
            return False


