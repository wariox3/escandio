"""Regresion: la red de la API movil (movil_exception_handler) convierte
excepciones que antes daban 500 opaco -> la app las mostraba como "servidor
fuera de linea" y entraba en bucle de re-sincronizacion. Ahora salen con el
envelope v2 {codigo, titulo, mensaje}.

- Model.DoesNotExist no atrapado -> 404.
- django ValidationError / FieldError -> 400.
- Un ValueError (pk no numerico) NO se atrapa aca a proposito: se valida por
  vista, para no enmascararle a Sentry otros ValueError que si serian bugs.

Correr: python manage.py test movil.tests.test_handler_500_movil
"""
from django.core.exceptions import FieldError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import RequestFactory, TestCase

from movil import responses
from movil.exceptions import movil_exception_handler
from ruteo.models.visita import RutVisita


class _FakeView:
    pass


def _contexto():
    return {'request': RequestFactory().post('/api/v2/novedades/'), 'view': _FakeView()}


class HandlerMovil500Tests(TestCase):

    def test_does_not_exist_da_404_con_envelope_v2(self):
        resp = movil_exception_handler(RutVisita.DoesNotExist(), _contexto())
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 404, resp.data)
        self.assertEqual(resp.data['codigo'], responses.COD_NO_ENCONTRADO)
        for clave in ('codigo', 'titulo', 'mensaje'):
            self.assertIn(clave, resp.data)

    def test_validation_error_da_400(self):
        resp = movil_exception_handler(DjangoValidationError('x'), _contexto())
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(resp.data['codigo'], responses.COD_PARAMETROS)

    def test_field_error_da_400(self):
        resp = movil_exception_handler(FieldError('x'), _contexto())
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(resp.data['codigo'], responses.COD_PARAMETROS)

    def test_value_error_no_se_atrapa_en_el_handler(self):
        # A proposito: el ValueError de pk no numerico se valida en cada vista
        # (coercion int()), no aca. El handler lo deja pasar -> None.
        resp = movil_exception_handler(
            ValueError("Field 'id' expected a number but got 'abc'."), _contexto(),
        )
        self.assertIsNone(resp)
