"""
Permisos por rol dentro de un contenedor.

Reglas:
- Super admin (User.is_superuser) tiene acceso a todo.
- Admin: User es FK de Contenedor.usuario en el tenant activo. 1 admin por contenedor.
- Usuario: existe UsuarioContenedor(usuario, contenedor, rol='usuario').

Permisos granulares (web): UsuarioContenedor.permisos es un JSON
{modulo: {'ver': bool, 'editar': bool}, ...}. Reemplaza al perfil_web fijo
para gating de endpoints web. perfil_movil se mantiene para la app movil
(ver contrato_movil.py).

Helpers:
- es_admin_del_contenedor(user, contenedor) -> bool
- es_miembro_del_contenedor(user, contenedor) -> bool
- rol_en_contenedor(user, contenedor) -> 'super_admin' | 'admin' | 'usuario' | None
- puede_ver(user, contenedor, modulo) -> bool
- puede_editar_modulo(user, contenedor, modulo) -> bool
- plantilla_permisos(nombre) -> dict (presets consulta/operativo/supervisor)

Permission classes para DRF:
- EsSuperAdmin
- EsAdminDelContenedor: admin del tenant activo (request.tenant)
- EsMiembroDelContenedor: admin o usuario invitado
- PermisoModuloVer(modulo) y PermisoModuloEditar(modulo): factories.
"""
from rest_framework.permissions import BasePermission

from django.db import connection


MODULOS = (
    'visita',
    'vehiculo',
    'despacho',
    'franja',
    'flota',
    'novedad',
    'contacto',
    'empresa',
    'configuracion',
    'mensajeria',
    'facturacion',
    'usuario',
)


def plantilla_permisos(nombre):
    """Devuelve el set de permisos preset para 'consulta', 'operativo' o 'supervisor'.
    consulta -> ver=True, editar=False en todos los modulos.
    operativo / supervisor -> ver=True, editar=True en todos.
    """
    if nombre == 'consulta':
        editar = False
    elif nombre in ('operativo', 'supervisor'):
        editar = True
    else:
        return {}
    return {modulo: {'ver': True, 'editar': editar} for modulo in MODULOS}


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
    """True si el user es admin o tiene UsuarioContenedor con acceso web o móvil."""
    if es_admin_del_contenedor(user, contenedor):
        return True
    if not (user and user.is_authenticated and contenedor):
        return False
    from django.db.models import Q
    from contenedor.models import UsuarioContenedor
    return UsuarioContenedor.objects.filter(
        Q(tiene_acceso_web=True) | Q(tiene_acceso_movil=True),
        usuario_id=user.id, contenedor_id=contenedor.id,
    ).exists()


def perfil_web_del_miembro(user, contenedor):
    """Devuelve el perfil_web del UsuarioContenedor o 'admin' si es admin/super_admin, None si no es miembro."""
    if es_super_admin(user) or es_admin_del_contenedor(user, contenedor):
        return 'admin'
    if not (user and user.is_authenticated and contenedor):
        return None
    from contenedor.models import UsuarioContenedor
    uc = UsuarioContenedor.objects.filter(
        usuario_id=user.id, contenedor_id=contenedor.id, tiene_acceso_web=True
    ).only('perfil_web').first()
    return uc.perfil_web if uc else None


def perfil_movil_del_miembro(user, contenedor):
    """Devuelve el perfil_movil del UsuarioContenedor o 'admin' si es admin/super_admin, None si no es miembro móvil."""
    if es_super_admin(user) or es_admin_del_contenedor(user, contenedor):
        return 'admin'
    if not (user and user.is_authenticated and contenedor):
        return None
    from contenedor.models import UsuarioContenedor
    uc = UsuarioContenedor.objects.filter(
        usuario_id=user.id, contenedor_id=contenedor.id, tiene_acceso_movil=True
    ).only('perfil_movil').first()
    return uc.perfil_movil if uc else None


def puede_editar(user, contenedor):
    """Pueden escribir: admin, super admin, perfiles web operativo/supervisor o cualquier perfil móvil activo.
    Solo se excluye perfil_web='consulta' sin acceso móvil."""
    perfil_w = perfil_web_del_miembro(user, contenedor)
    if perfil_w in ('admin', 'operativo', 'supervisor'):
        return True
    perfil_m = perfil_movil_del_miembro(user, contenedor)
    return perfil_m in ('admin', 'conductor', 'coordinador')


def _permisos_membresia(user, contenedor):
    """Devuelve el JSON de permisos del UsuarioContenedor o None."""
    if not (user and user.is_authenticated and contenedor):
        return None
    from contenedor.models import UsuarioContenedor
    uc = UsuarioContenedor.objects.filter(
        usuario_id=user.id, contenedor_id=contenedor.id, tiene_acceso_web=True
    ).only('permisos').first()
    return uc.permisos if uc else None


def puede_ver(user, contenedor, modulo):
    """True si el usuario puede ver el modulo en este contenedor.
    Admin y super admin tienen acceso total."""
    if es_super_admin(user) or es_admin_del_contenedor(user, contenedor):
        return True
    permisos = _permisos_membresia(user, contenedor)
    if not permisos:
        return False
    return bool(permisos.get(modulo, {}).get('ver'))


def puede_editar_modulo(user, contenedor, modulo):
    """True si el usuario puede editar el modulo en este contenedor.
    Admin y super admin tienen acceso total."""
    if es_super_admin(user) or es_admin_del_contenedor(user, contenedor):
        return True
    permisos = _permisos_membresia(user, contenedor)
    if not permisos:
        return False
    return bool(permisos.get(modulo, {}).get('editar'))


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


class EsMiembroEditor(BasePermission):
    """Admin, super admin, operativo o supervisor — excluye perfil 'consulta'."""
    message = 'Tu perfil es de solo lectura.'

    def has_permission(self, request, view):
        contenedor = _resolver_contenedor(request)
        return puede_editar(request.user, contenedor)


def PermisoModuloVer(modulo):
    """Factory: permission class que exige permiso 'ver' sobre el modulo dado."""

    class _Permiso(BasePermission):
        message = f'No tienes permiso para ver {modulo}.'

        def has_permission(self, request, view):
            contenedor = _resolver_contenedor(request)
            return puede_ver(request.user, contenedor, modulo)

    _Permiso.__name__ = f'PermisoModuloVer_{modulo}'
    return _Permiso


def PermisoModuloEditar(modulo):
    """Factory: permission class que exige permiso 'editar' sobre el modulo dado."""

    class _Permiso(BasePermission):
        message = f'No tienes permiso para editar {modulo}.'

        def has_permission(self, request, view):
            contenedor = _resolver_contenedor(request)
            return puede_editar_modulo(request.user, contenedor, modulo)

    _Permiso.__name__ = f'PermisoModuloEditar_{modulo}'
    return _Permiso
