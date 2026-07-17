"""Exception handler de la API movil v2.

Normaliza cualquier error de DRF al envelope {codigo, titulo, mensaje} para que
la app movil tenga un unico formato de error que parsear. Se activa por-vista
via MovilApiMixin.get_exception_handler (no reemplaza el handler global).
"""
from django.core.exceptions import (
    ObjectDoesNotExist,
    ValidationError as DjangoValidationError,
    FieldError,
)
from rest_framework.views import exception_handler

from movil import responses

_POR_STATUS = {
    400: (responses.COD_PARAMETROS, 'Datos invalidos'),
    401: (responses.COD_NO_AUTENTICADO, 'Sesion requerida'),
    403: (responses.COD_SIN_PERMISO, 'Sin acceso'),
    404: (responses.COD_NO_ENCONTRADO, 'No encontrado'),
    405: (responses.COD_PARAMETROS, 'Metodo no permitido'),
    406: (responses.COD_PARAMETROS, 'Formato no aceptado'),
    415: (responses.COD_PARAMETROS, 'Formato no soportado'),
    429: (responses.COD_CONFLICTO, 'Demasiadas solicitudes'),
}


def _mensaje_de(data):
    """Extrae un mensaje legible del cuerpo de error que arma DRF."""
    if isinstance(data, dict):
        if 'detail' in data:
            return str(data['detail'])
        for valor in data.values():
            if isinstance(valor, (list, tuple)) and valor:
                return str(valor[0])
            if valor:
                return str(valor)
    if isinstance(data, (list, tuple)) and data:
        return str(data[0])
    return str(data)


def movil_exception_handler(exc, context):
    # Excepciones que DRF NO atrapa (exception_handler devuelve None): hoy se
    # vuelven 500 opaco -> la app muestra "servidor fuera de linea" y entra en
    # bucle de re-sincronizacion. Las normalizamos al envelope v2 ANTES de que
    # se vuelvan 500:
    #  - Model.objects.get(...)/related sin atrapar -> DoesNotExist -> 404.
    #  - fecha/numero mal formado en un filtro (django ValidationError) o campo
    #    inexistente en filter()/values() (FieldError) -> 400.
    # (El pk no numerico -> ValueError se valida en cada vista, NO aca, para no
    # enmascararle a Sentry otros ValueError que si serian bugs reales.)
    if isinstance(exc, ObjectDoesNotExist):
        return responses.error(
            'No existe el registro solicitado', responses.COD_NO_ENCONTRADO, 404,
            titulo='No encontrado',
        )
    if isinstance(exc, (DjangoValidationError, FieldError)):
        return responses.error(
            'Datos invalidos en la solicitud', responses.COD_PARAMETROS, 400,
            titulo='Datos invalidos',
        )

    response = exception_handler(exc, context)
    if response is None:
        return None
    codigo, titulo = _POR_STATUS.get(
        response.status_code, (responses.COD_SERVIDOR, 'Error'),
    )
    cuerpo = {'codigo': codigo, 'titulo': titulo, 'mensaje': _mensaje_de(response.data)}
    # En errores de validacion conservamos el detalle por campo.
    if (response.status_code == 400 and isinstance(response.data, dict)
            and 'detail' not in response.data):
        cuerpo['validaciones'] = response.data
    response.data = cuerpo
    return response
