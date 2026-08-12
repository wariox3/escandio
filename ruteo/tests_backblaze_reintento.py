"""subir_data reintenta ante errores de B2 (p.ej. UploadTokenUsedConcurrently).

Al mover la subida de evidencias fuera de la transaccion de entrega, se perdio
el reintento implicito (que antes daba el rollback + reenvio del movil). Este
reintento lo repone a nivel del cliente Backblaze.

Correr: python manage.py test ruteo.tests_backblaze_reintento
"""
from unittest.mock import MagicMock, patch

from b2sdk.v2.exception import B2Error
from django.test import SimpleTestCase

from utilidades.backblaze import Backblaze


class BackblazeReintentoTests(SimpleTestCase):

    def _backblaze(self, bucket):
        # __new__ evita __init__ (que autoriza cuenta y pega a la red).
        bb = Backblaze.__new__(Backblaze)
        bb.b2_api = MagicMock()
        bb.b2_api.get_bucket_by_name.return_value = bucket
        return bb

    @patch('utilidades.backblaze.config', lambda k: 'ruteoco')
    @patch('utilidades.backblaze.time.sleep', lambda *a: None)
    def test_reintenta_ante_error_y_tiene_exito(self):
        bucket = MagicMock()
        ok = MagicMock(id_='f1', size=10, content_type='image/png')
        bucket.upload_bytes.side_effect = [B2Error('busy'), B2Error('busy'), ok]

        result = self._backblaze(bucket).subir_data(b'data', 'energy', 'foto.png')

        self.assertEqual(result[0], 'f1')
        self.assertEqual(bucket.upload_bytes.call_count, 3)

    @patch('utilidades.backblaze.config', lambda k: 'ruteoco')
    @patch('utilidades.backblaze.time.sleep', lambda *a: None)
    def test_reranza_tras_agotar_los_intentos(self):
        bucket = MagicMock()
        bucket.upload_bytes.side_effect = B2Error('busy')

        with self.assertRaises(B2Error):
            self._backblaze(bucket).subir_data(b'data', 'energy', 'foto.png', intentos=3)

        self.assertEqual(bucket.upload_bytes.call_count, 3)

    # -- descargar: B2 puede tirar un 500 transitorio (internal_error) ---------
    @patch('utilidades.backblaze.config', lambda k: 'ruteoco')
    @patch('utilidades.backblaze.time.sleep', lambda *a: None)
    def test_descargar_reintenta_ante_error_y_tiene_exito(self):
        bucket = MagicMock()
        ok = MagicMock(response='contenido')
        bucket.download_file_by_id.side_effect = [B2Error('500'), ok]

        result = self._backblaze(bucket).descargar('archivo-id')

        self.assertEqual(result, 'contenido')
        self.assertEqual(bucket.download_file_by_id.call_count, 2)

    @patch('utilidades.backblaze.config', lambda k: 'ruteoco')
    @patch('utilidades.backblaze.time.sleep', lambda *a: None)
    def test_descargar_reranza_tras_agotar_los_intentos(self):
        bucket = MagicMock()
        bucket.download_file_by_id.side_effect = B2Error('500')

        with self.assertRaises(B2Error):
            self._backblaze(bucket).descargar('archivo-id', intentos=3)

        self.assertEqual(bucket.download_file_by_id.call_count, 3)
