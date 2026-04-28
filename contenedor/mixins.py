"""
Mixins reusables para viewsets multi-tenant con roles.

RolMixin:
- Por defecto, exige que el user sea miembro del contenedor (admin o usuario invitado).
- Las acciones definidas en `acciones_admin` exigen rol admin (o super admin).

Uso:
    class RutVehiculoViewSet(RolMixin, viewsets.ModelViewSet):
        acciones_admin = ['create', 'update', 'partial_update', 'destroy']
        ...
"""
from rest_framework.permissions import IsAuthenticated

from contenedor.permisos import EsAdminDelContenedor, EsMiembroDelContenedor


class RolMixin:
    acciones_admin: list = []

    def get_permissions(self):
        permisos = [IsAuthenticated()]
        if self.action in (self.acciones_admin or []):
            permisos.append(EsAdminDelContenedor())
        else:
            permisos.append(EsMiembroDelContenedor())
        return permisos
