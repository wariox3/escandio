"""
Permisos por rol dentro de un contenedor.

Reglas:
- Super admin (User.is_superuser) tiene acceso a todo.
- Admin: User es FK de Contenedor.usuario en el tenant activo. 1 admin por contenedor.
- Usuario: existe UsuarioContenedor(usuario, contenedor, rol='usuario').

Helpers:
- es_admin_del_contenedor(user, contenedor) -> bool
- es_miembro_del_contenedor(user, contenedor) -> bool
- rol_en_contenedor(user, contenedor) -> 'super_admin' | 'admin' | 'usuario' | None

Permission classes para DRF:
- EsSuperAdmin
- EsAdminDelContenedor: admin del tenant activo (request.tenant)
- EsMiembroDelContenedor: admin o usuario invitado
"""
from rest_framework.permissions import BasePermission

from django.db import connection


def _resolver_contenedor(request):
    """Obtiene el contenedor del request (django_tenants lo expone como request.tenant)."""
    return getattr(request, 'tenant', None)


def es_super_admin(user):
    return bool(user and user.is_authenticated and user.is_superuser)


def es_admin_del_contenedor(user, contenedor):
    if not (user and user.is_authenticated):
        return False
    if not contenedor:
        return False
    return contenedor.usuario_id == user.id


def es_miembro_del_contenedor(user, contenedor):
    """True si el user es admin o tiene UsuarioContenedor en el contenedor."""
    if es_admin_del_contenedor(user, contenedor):
        return True
    if not (user and user.is_authenticated and contenedor):
        return False
    # Import local para evitar circular
    from contenedor.models import UsuarioContenedor
    # Las relaciones UsuarioContenedor viven en el schema public, no en el tenant
    return UsuarioContenedor.objects.filter(
        usuario_id=user.id, contenedor_id=contenedor.id
    ).exists()


def rol_en_contenedor(user, contenedor):
    """Devuelve 'super_admin' | 'admin' | 'usuario' | None."""
    if es_super_admin(user):
        return 'super_admin'
    if es_admin_del_contenedor(user, contenedor):
        return 'admin'
    if es_miembro_del_contenedor(user, contenedor):
        return 'usuario'
    return None


class EsSuperAdmin(BasePermission):
    message = 'Solo el super administrador puede realizar esta acción.'

    def has_permission(self, request, view):
        return es_super_admin(request.user)


class EsAdminDelContenedor(BasePermission):
    """Solo el admin (FK Contenedor.usuario) o un super admin puede operar."""
    message = 'Solo el administrador del contenedor puede realizar esta acción.'

    def has_permission(self, request, view):
        if es_super_admin(request.user):
            return True
        contenedor = _resolver_contenedor(request)
        return es_admin_del_contenedor(request.user, contenedor)


class EsMiembroDelContenedor(BasePermission):
    """Admin, usuario invitado o super admin pueden operar."""
    message = 'No tienes acceso a este contenedor.'

    def has_permission(self, request, view):
        if es_super_admin(request.user):
            return True
        contenedor = _resolver_contenedor(request)
        return es_miembro_del_contenedor(request.user, contenedor)
