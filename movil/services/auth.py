"""Logica de autenticacion v2.

Reimplementa el alta de usuario y la solicitud de cambio de clave del flujo
legacy (contenedor.views.usuario) sin tocar las views congeladas.
"""
import secrets
from datetime import datetime, timedelta

from decouple import config

from contenedor.models import User
from contenedor.serializers.user import UserSerializer
from contenedor.serializers.verificacion import CtnVerificacionSerializador
from utilidades.zinc import Zinc


def _url_app(ruta, token):
    env = config('ENV', default='prod').lower()
    if env == 'dev':
        base = 'http://localhost:4200'
    elif env == 'test':
        base = 'http://app.ruteo.online'
    else:
        base = 'https://app.ruteo.co'
    return f'{base}/{ruta}/{token}'


def _enviar_correo(usuario, asunto, html):
    """Envia un correo sin propagar la excepcion: el flujo no debe fallar por esto."""
    try:
        Zinc().correo(usuario.correo, asunto, html, 'ruteo')
        return True
    except Exception:  # noqa: BLE001
        return False


def crear_usuario(username, password, nombre=None, telefono=None, empresa_nombre=None):
    """Crea el usuario (pendiente de aprobacion) y dispara el correo de verificacion.

    Devuelve (usuario, errores). Si errores no es None no se creo nada.
    El auto-registro v2 queda en `estado_registro='pendiente'`: el super-admin
    debe asignarlo a un contenedor para que tenga acceso.
    """
    serializador = UserSerializer(data={'username': username, 'password': password})
    if not serializador.is_valid():
        return None, serializador.errors
    usuario = serializador.save()

    usuario.estado_registro = 'pendiente'
    if nombre:
        usuario.nombre = nombre
    if telefono:
        usuario.telefono = telefono
    if empresa_nombre:
        usuario.empresa_nombre = empresa_nombre
    usuario.save(update_fields=['estado_registro', 'nombre', 'telefono', 'empresa_nombre'])

    token = secrets.token_urlsafe(20)
    verificacion = CtnVerificacionSerializador(data={
        'usuario_id': usuario.id,
        'token': token,
        'vence': datetime.now().date() + timedelta(days=1),
    })
    if verificacion.is_valid():
        verificacion.save()
        html = (
            f"<h1>Hola {usuario.nombre_corto}!</h1>"
            f"<p>Verifica tu cuenta de Ruteo.co haciendo clic en el enlace.</p>"
            f"<a href='{_url_app('auth/verificacion', token)}'>Verificar cuenta</a>"
        )
        _enviar_correo(usuario, 'Verificar cuenta de Ruteo.co', html)
    return usuario, None


def solicitar_cambio_clave(username):
    """Crea una verificacion de cambio de clave y envia el correo.

    Devuelve (ok, usuario). ok=False si el usuario no existe.
    """
    usuario = User.objects.filter(username=username).first()
    if usuario is None:
        return False, None

    token = secrets.token_urlsafe(20)
    verificacion = CtnVerificacionSerializador(data={
        'usuario_id': usuario.id,
        'token': token,
        'vence': datetime.now().date() + timedelta(days=1),
        'accion': 'clave',
    })
    if verificacion.is_valid():
        verificacion.save()
        html = (
            f"<h1>Hola {usuario.nombre_corto}!</h1>"
            f"<p>Recibimos una solicitud para cambiar tu clave.</p>"
            f"<a href='{_url_app('auth/clave/cambiar', token)}'>Cambiar clave</a>"
        )
        _enviar_correo(usuario, 'Solicitud cambio clave Ruteo.co', html)
    return True, usuario
