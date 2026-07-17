"""Regresion: la red de seguridad central de custom_exception_handler convierte
excepciones que antes daban 500 opaco ("servidor fuera de linea") en respuestas
limpias para TODA la API web, en un solo lugar.

- Model.DoesNotExist NO atrapado en la vista -> 404 (antes 500).
- django ValidationError / FieldError (fecha o campo invalido en un filtro del
  ORM) -> 400 (antes 500).

Se ejerce el handler directamente (sin HTTP), mismo patron que
ruteo/tests_borrado_protegido.py y ruteo/tests_permisos_operativos.py.

Correr: python manage.py test ruteo.tests_handler_500
"""
from django.core.exceptions import FieldError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import RequestFactory, TestCase

from escandioapp.exceptions import custom_exception_handler
from ruteo.models.visita import RutVisita


class _FakeView:
    """En la rama de red de seguridad el handler no toca la vista."""


def _contexto(metodo='get', ruta='/ruteo/visita/9/'):
    return {'request': getattr(RequestFactory(), metodo)(ruta), 'view': _FakeView()}


class RedSeguridad500Tests(TestCase):

    def test_does_not_exist_no_atrapado_da_404(self):
        # Un `RutVisita.objects.get(...)` crudo que no existe: antes 500, ahora
        # 404 limpio. DoesNotExist es subclase de ObjectDoesNotExist.
        resp = custom_exception_handler(RutVisita.DoesNotExist(), _contexto())
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 404, resp.data)
        self.assertEqual(resp.data['codigo'], 15)

    def test_django_validation_error_da_400(self):
        # p.ej. `?fecha_desde=abc` usado en un filter(fecha__date__gte=...).
        resp = custom_exception_handler(DjangoValidationError('fecha invalida'), _contexto())
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(resp.data['codigo'], 14)

    def test_field_error_da_400(self):
        # p.ej. `.values(*campos)` o `.filter(campo_inexistente=...)`.
        resp = custom_exception_handler(FieldError('Cannot resolve keyword'), _contexto())
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(resp.data['codigo'], 14)
