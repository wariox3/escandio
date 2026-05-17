"""Base comun de las vistas de la API movil v2."""
from movil.exceptions import movil_exception_handler


class MovilApiMixin:
    """Hace que la vista use el envelope de error v2 {codigo, titulo, mensaje}."""

    def get_exception_handler(self):
        return movil_exception_handler
