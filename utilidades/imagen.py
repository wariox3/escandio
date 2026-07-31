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

            # draft() le pide al decoder de JPEG que decodifique a una escala
            # cercana al tamano final (1/2, 1/4, 1/8) SIN cargar la imagen a
            # resolucion completa en RAM. Baja el pico de memoria ~10x en fotos
            # grandes de celular: la fuga venia de convert()/resize() decodificando
            # el JPEG entero (pico de 50-150 MB por foto que glibc no devolvia).
            # Es no-op para formatos que no son JPEG.
            if max_width:
                img.draft('RGB', (max_width, max_width))

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




