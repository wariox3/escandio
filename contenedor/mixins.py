"""
Mixins reusables para viewsets multi-tenant con roles y perfiles.

RolMixin gating:
- acciones_publicas → solo IsAuthenticated (escape hatch para móvil).
- acciones_admin → solo admin del contenedor (o super admin).
- acciones_lectura → cualquier miembro (incluido perfil 'consulta').
- Acciones CRUD estándar (create/update/partial_update/destroy) → editor
  (admin, operativo, supervisor). Perfil 'consulta' queda fuera.
- list/retrieve por defecto son lectura para todos los miembros.

Uso:
    class RutVehiculoViewSet(RolMixin, viewsets.ModelViewSet):
        acciones_admin = ['create', 'update', 'partial_update', 'destroy']
"""
from rest_framework.permissions import IsAuthenticated

from contenedor.permisos import (
    EsAdminDelContenedor,
    EsMiembroDelContenedor,
    EsMiembroEditor,
)

ACCIONES_DE_LECTURA = {'list', 'retrieve'}
ACCIONES_DE_ESCRITURA = {'create', 'update', 'partial_update', 'destroy'}


class RolMixin:
    acciones_admin: list = []
    acciones_lectura: list = []
    acciones_publicas: list = []

    def get_permissions(self):
        permisos = [IsAuthenticated()]
        if self.action in (self.acciones_publicas or []):
            return permisos
        if self.action in (self.acciones_admin or []):
            permisos.append(EsAdminDelContenedor())
        elif self.action in ACCIONES_DE_LECTURA or self.action in (self.acciones_lectura or []):
            permisos.append(EsMiembroDelContenedor())
        elif self.action in ACCIONES_DE_ESCRITURA:
            permisos.append(EsMiembroEditor())
        else:
            # Acciones @action custom: por defecto requieren editor
            permisos.append(EsMiembroEditor())
        return permisos
