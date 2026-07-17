"""Regresion: borrar un registro en uso (FK on_delete=PROTECT/RESTRICT) no debe
dar un 500 opaco ("Servidor fuera de linea") ni ensuciar Sentry con un falso
"bug" — es una accion invalida esperada del usuario, no un error del servidor.

Reportado via Sentry (jul 2026): DELETE /ruteo/vehiculo/9/ con el vehiculo aun
asignado a una ruta (RutDespacho #106) y una flota (RutFlota #9) lanzaba
ProtectedError sin manejar -> 500. El fix vive en
escandioapp.exceptions.custom_exception_handler y aplica a TODA la API
(vehiculo, conductor, franja, ...): convierte ProtectedError/RestrictedError en
un 409 con mensaje claro, y hasta enumera EN QUE esta en uso.

Se ejerce el handler directamente (sin HTTP ni DB), mismo patron que
ruteo/tests_permisos_operativos.py.

Correr: python manage.py test ruteo.tests_borrado_protegido
"""
from django.db.models import ProtectedError, RestrictedError
from django.test import RequestFactory, TestCase

from escandioapp.exceptions import custom_exception_handler
from ruteo.models.despacho import RutDespacho
from ruteo.models.flota import RutFlota


class _FakeView:
    """El handler solo lee view.__class__ para logs de excepciones NO manejadas;
    en la rama ProtectedError ni se toca. Basta un objeto cualquiera."""


def _contexto(metodo='delete', ruta='/ruteo/vehiculo/9/'):
    request = getattr(RequestFactory(), metodo)(ruta)
    return {'request': request, 'view': _FakeView()}


class BorradoProtegidoTests(TestCase):

    def test_protected_error_da_409_y_enumera_los_tipos_en_uso(self):
        # Instancias sin guardar: el handler solo lee su clase para el mensaje
        # (no toca la DB). pk explicito para que sean hashables en el set.
        exc = ProtectedError(
            'Cannot delete', {RutDespacho(id=106), RutFlota(id=9)},
        )
        resp = custom_exception_handler(exc, _contexto())

        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 409, resp.data)
        self.assertEqual(resp.data['codigo'], 16)
        # El mensaje le dice al usuario DONDE esta en uso para que lo desasocie.
        self.assertIn('rutas', resp.data['mensaje'])
        self.assertIn('flotas', resp.data['mensaje'])

    def test_restricted_error_tambien_da_409(self):
        # RestrictedError expone .restricted_objects (no .protected_objects);
        # el helper cubre ambos, asi que igual enumera el tipo.
        exc = RestrictedError('Cannot delete', {RutDespacho(id=1)})
        resp = custom_exception_handler(exc, _contexto())

        self.assertEqual(resp.status_code, 409, resp.data)
        self.assertEqual(resp.data['codigo'], 16)
        self.assertIn('rutas', resp.data['mensaje'])

    def test_modelo_no_mapeado_cae_a_mensaje_generico_sigue_409(self):
        # Un objeto de clase desconocida no rompe el armado del mensaje: cae al
        # texto generico y mantiene el 409 (nunca vuelve a ser 500).
        exc = ProtectedError('Cannot delete', {object()})
        resp = custom_exception_handler(exc, _contexto())

        self.assertEqual(resp.status_code, 409, resp.data)
        self.assertEqual(resp.data['codigo'], 16)
        self.assertIn('otros', resp.data['mensaje'].lower())
