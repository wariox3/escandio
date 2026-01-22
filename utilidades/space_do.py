import boto3
import base64
#import magic
from decouple import config 
from botocore.config import Config
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
from io import BytesIO

class SpaceDo():
    #documentacion: https://docs.digitalocean.com/products/spaces/reference/s3-sdk-examples/
        #Listar los buckets
        #response = client.list_buckets()
        #for space in response['Buckets']:
        #    print(space['Name'])
        #Listar archivos del bucket
        #response = client.list_objects(Bucket='semantica')
        #for obj in response['Contents']:
        #    print(obj['Key'])


    def __init__(self):
        session = boto3.session.Session()
        self.client = session.client('s3',
                            config=Config(s3={'addressing_style': 'virtual'}),
                            region_name=config('DO_REGION'),
                            endpoint_url=f"https://{config('DO_REGION')}.digitaloceanspaces.com",                        
                            aws_access_key_id=config('DO_CLAVE_ACCESO'),
                            aws_secret_access_key=config('DO_CLAVE_SECRETA')) 

    def upload(self, pathArchivo):                                
        self.client.upload_file(pathArchivo, config('DO_BUCKET'), 'prueba/Captura.JPG')

    def put(self, pathArchivo, pathDestino):
        with open(pathArchivo, 'rb') as file:
            #metadata = magic.from_file(pathArchivo, mime=True)
            metadata = ''
            self.client.put_object(Bucket=config('DO_BUCKET'),
                    #Key='prueba/logo_ejemplo.jpg',
                    Key=pathDestino,
                    Body=file,
                    ACL='public-read',
                    ContentType=metadata)
            
    def putB64(self, path_destino, b64, contentType):
        imagen_bytes = base64.b64decode(b64)
        imagen_temporal = BytesIO(imagen_bytes)
        imagen_temporal.seek(0)
        extra_args = {
            'ACL': 'public-read',
            'ContentType': contentType
            }
        self.client.upload_fileobj(imagen_temporal, config('DO_BUCKET'), path_destino, ExtraArgs=extra_args)    

    def eliminar(self, pathDestino):
        if pathDestino and pathDestino.strip() != "itrio/usuario_defecto.jpg" and pathDestino.strip() != "itrio/logo_defecto.jpg" and pathDestino.strip() != "itrio/item_defecto.jpg":
            self.client.delete_object(Bucket=config('DO_BUCKET'), Key=pathDestino)

    def descargar(self, path):
        try:
            file_obj = self.client.get_object(Bucket=config('DO_BUCKET'), Key=path)        
            pdf_data = file_obj['Body'].read()
            return {'error':False, 'data':pdf_data}

        except ClientError as e:
            if e.response['Error']['Code'] == 'AccessDenied':
                return {'error':True, 'mensaje':'No se encuentra el archivo'}
            else:
                return {'error':True, 'mensaje':f"Error no especificado {str(e)}"} 
            
    def listar_bukets(self):
        try:
            response = self.client.list_buckets()
            print("Conexión exitosa. Buckets disponibles:")
            for bucket in response.get('Buckets', []):
                print(f"- {bucket['Name']}")  
        except Exception as e:
            print("Error de conexión:", e)                     