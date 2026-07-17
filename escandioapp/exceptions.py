from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.db.models import ProtectedError, RestrictedError
from decouple import config
import requests
import django
import traceback
import logging

logger = logging.getLogger('escandioapp.exceptions')

# Nombres amigables (dominio) para los modelos que suelen bloquear un borrado por
# FK protegida. Si el modelo no esta aca, el mensaje cae a la version generica.
_MODELOS_EN_USO = {
    'RutDespacho': 'rutas',
    'RutFlota': 'flotas',
    'RutVisita': 'guías',
    'RutFranja': 'zonas',
    'RutVehiculo': 'vehículos',
    'RutConductor': 'conductores',
    'RutNovedad': 'novedades',
}


def _tipos_que_bloquean(exc):
    """Tipos de registro (en palabras del dominio, sin repetir) que impiden el
    borrado. Best-effort: los modelos no mapeados se omiten del detalle.

    ProtectedError expone .protected_objects y RestrictedError .restricted_objects;
    cubrimos ambos para no perder el detalle segun el tipo de FK."""
    objetos = (getattr(exc, 'protected_objects', None)
               or getattr(exc, 'restricted_objects', None) or [])
    nombres = []
    for obj in objetos:
        amigable = _MODELOS_EN_USO.get(obj.__class__.__name__)
        if amigable and amigable not in nombres:
            nombres.append(amigable)
    return nombres


def custom_exception_handler(exc, context):
    # Borrado bloqueado por FK protegida (on_delete=PROTECT/RESTRICT): p.ej.
    # eliminar un vehiculo que sigue asignado a rutas o flotas. Sin manejar,
    # Django responde 500 opaco ("Servidor fuera de linea") y ademas ensucia
    # Sentry con un "bug" que en realidad es una accion invalida del usuario.
    # Lo convertimos en un 409 con mensaje claro para TODA la API (vehiculo,
    # conductor, franja, ...), no solo el endpoint donde se reporto.
    if isinstance(exc, (ProtectedError, RestrictedError)):
        tipos = _tipos_que_bloquean(exc)
        if tipos:
            mensaje = ('No se puede eliminar porque está en uso en: '
                       f'{", ".join(tipos)}. Quítalo de ahí antes de eliminarlo.')
        else:
            mensaje = ('No se puede eliminar porque está siendo usado por otros '
                       'registros. Quítalo de donde se usa antes de eliminarlo.')
        # info (no error): es una accion invalida esperada, no un bug -> no debe
        # generar issue en Sentry, pero deja rastro de cuanto ocurre.
        logger.info('Borrado bloqueado por FK protegida en %s %s: %s',
                    context['request'].method, context['request'].path, mensaje)
        return Response({'mensaje': mensaje, 'codigo': 16},
                        status=status.HTTP_409_CONFLICT)

    response = exception_handler(exc, context)
    if response is not None:
        if response.status_code == 404:
            response.data = {
                'mensaje': 'No existe',
                'codigo': 15
            }
        if response.status_code == 400:
            response.data = {
                'mensaje': 'Mensajes de validación',
                'codigo': 14,
                'validaciones': response.data
            } 
    else:
        request = context['request']
        mensaje = str(exc)
        usuario = request.user.username if request.user.is_authenticated else 'anonimo'
        contenedor = getattr(request, 'tenant', '') 
        usuario_objeto = {
            'id': request.user.id,
            'username': request.user.username,
            'correo': request.user.correo,
            'nombre_corto': request.user.nombre_corto,            
            'is_active': request.user.is_active,
            'is_staff': request.user.is_staff,
        } if request.user.is_authenticated else None  
        traceback_completo = traceback.format_exc()
        django_version = django.get_version()
        traza = {
            "request_method": request.method,
            "request_url": request.build_absolute_uri(),
            "django_version": django_version,
            "exception_type": exc.__class__.__name__,
            "exception_value": str(exc),
            "exception_location": traceback_completo,
            "raised_during": f"{context['view'].__class__.__module__}.{context['view'].__class__.__name__}",
        }

        datos = {
            'mensaje': mensaje,
            'archivo': "path",
            'ruta': request.path,
            'usuario': usuario,
            'usuario_objeto': usuario_objeto,
            'traza': traceback_completo,
            'traza_objeto': traza,
            'entorno': config('ENV'),
            'contenedor': '',
            'contenedor_objeto': [],
            'data': request.data
        }
        # Excepcion NO manejada (DRF devolvio response=None -> Django respondera
        # 500, que el movil muestra como "Servidor fuera de linea"). Antes el
        # traceback se construia y se DESCARTABA, dejando el 500 sin rastro y
        # sin forma de saber la causa. Lo logueamos con exc_info para que quede
        # en los logs del servidor (stderr/gunicorn) y se pueda diagnosticar.
        logger.error(
            "Excepcion no manejada [%s] en %s %s (view=%s, usuario=%s): %s",
            exc.__class__.__name__,
            request.method,
            request.path,
            traza.get('raised_during'),
            usuario,
            mensaje,
            exc_info=exc,
        )
    return response