from general.models.complemento import GenComplemento
from decouple import config
import requests
import json
from requests.auth import HTTPBasicAuth
from io import BytesIO
from PIL import Image

class Imagen:
    @classmethod
    def comprimir_imagen_jpg(cls, imagen, calidad=85, max_width=None):
        try:
            img = Image.open(imagen)
            
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            if max_width and img.width > max_width:
                ratio = max_width / float(img.width)
                height = int(float(img.height) * float(ratio))
                img = img.resize((max_width, height), Image.LANCZOS)
            
            output = BytesIO()
            img.save(output, format='JPEG', quality=calidad, optimize=True)
            compressed_data = output.getvalue()
            output.close()
            
            return compressed_data
            
        except Exception as e:
            if hasattr(imagen, 'read'):
                imagen.seek(0)
                return imagen.read()
            return imagen




