"""Helpers de respuesta de la API movil v2.

Envelope de error unico: {codigo, titulo, mensaje}. Ver movil/contrato_v2.py.
"""
from rest_framework.response import Response

# Codigos de error estables del contrato v2. La app movil los mapea a UX.
COD_PARAMETROS = 1       # faltan parametros o fallan validaciones
COD_CREDENCIALES = 2     # usuario o clave incorrectos
COD_NO_AUTENTICADO = 3   # token ausente, vencido o invalido
COD_SIN_PERMISO = 4      # autenticado pero sin acceso al recurso
COD_NO_ENCONTRADO = 5    # el recurso no existe
COD_CONFLICTO = 6        # estado ya procesado o duplicado
COD_SERVIDOR = 9         # error interno


def error(mensaje, codigo, status, titulo='Error', extra=None):
    """Construye una Response con el envelope de error v2."""
    cuerpo = {'codigo': codigo, 'titulo': titulo, 'mensaje': mensaje}
    if extra:
        cuerpo.update(extra)
    return Response(cuerpo, status=status)
