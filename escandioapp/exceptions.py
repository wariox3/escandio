from rest_framework.views import exception_handler
from decouple import config
import requests
import django
import traceback

def custom_exception_handler(exc, context):
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
        requests.post(
            'http://niquel.semantica.com.co/api/error/nuevo',
            json=datos,
            headers={'Content-Type': 'application/json'},
            timeout=5
        )
    return response