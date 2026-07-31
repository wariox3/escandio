"""comprimir_imagen_jpg: redimensiona bien con draft() (fix de la fuga de RAM).

draft() baja el pico de memoria decodificando el JPEG a escala reducida; estos
tests verifican que la salida sigue siendo un JPEG correcto al tamano esperado.

Correr: python manage.py test ruteo.tests_imagen
"""
import io

from django.test import SimpleTestCase
from PIL import Image

from utilidades.imagen import Imagen


class ComprimirImagenTests(SimpleTestCase):

    def _jpeg(self, ancho, alto):
        buffer = io.BytesIO()
        Image.new('RGB', (ancho, alto), (120, 90, 60)).save(buffer, format='JPEG')
        buffer.seek(0)
        return buffer

    def test_redimensiona_a_max_width_exacto(self):
        data = Imagen.comprimir_imagen_jpg(self._jpeg(4000, 3000), calidad=20, max_width=1920)
        salida = Image.open(io.BytesIO(data))
        self.assertEqual(salida.format, 'JPEG')
        self.assertEqual(salida.width, 1920)          # exacto tras el resize
        self.assertEqual(salida.height, 1440)         # mantiene proporcion

    def test_no_agranda_imagen_menor_al_maximo(self):
        data = Imagen.comprimir_imagen_jpg(self._jpeg(800, 600), calidad=20, max_width=1920)
        salida = Image.open(io.BytesIO(data))
        self.assertEqual((salida.width, salida.height), (800, 600))
