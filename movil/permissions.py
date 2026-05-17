"""Permisos de la API movil v2.

A diferencia del contrato legacy v1.6.4 (que usa el escape hatch
`acciones_publicas` para exigir solo IsAuthenticated), la v2 tiene viewsets
dedicados y puede gatear de forma explicita: el usuario debe estar autenticado
y tener acceso movil al contenedor del request.
"""
from rest_framework.permissions import BasePermission

from contenedor.permisos import es_admin_del_contenedor, es_super_admin


class EsConductorMovil(BasePermission):
    """Autenticado y con acceso movil al contenedor (tenant) del request.

    Admin del contenedor y super admin pasan siempre. El resto necesita un
    `UsuarioContenedor` con `tiene_acceso_movil=True` en el tenant activo.
    """

    message = 'No tienes acceso movil a este contenedor.'

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if es_super_admin(user):
            return True
        contenedor = getattr(request, 'tenant', None)
        if contenedor is None:
            return False
        if es_admin_del_contenedor(user, contenedor):
            return True
        # Un auto-registro pendiente o rechazado no accede a tenants hasta que
        # el super-admin lo apruebe asignandolo a un contenedor.
        if user.estado_registro != 'aprobado':
            return False
        from contenedor.models import UsuarioContenedor
        return UsuarioContenedor.objects.filter(
            usuario_id=user.id,
            contenedor_id=contenedor.id,
            tiene_acceso_movil=True,
        ).exists()
