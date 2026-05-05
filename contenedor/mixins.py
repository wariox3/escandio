"""
Mixins reusables para viewsets multi-tenant con roles y perfiles.

RolMixin gating:
- acciones_publicas → solo IsAuthenticated (escape hatch para móvil).
- acciones_admin → solo admin del contenedor (o super admin).
- acciones_lectura → cualquier miembro (incluido perfil 'consulta').
- Acciones CRUD estándar (create/update/partial_update/destroy) → editor
  (admin, operativo, supervisor). Perfil 'consulta' queda fuera.
- list/retrieve por defecto son lectura para todos los miembros.

Si el viewset declara `modulo`, list/retrieve exigen puede_ver(modulo)
y create/update/partial_update/destroy exigen puede_editar_modulo(modulo).
Esto reemplaza el chequeo legacy basado en perfil_web. Las acciones del
contrato móvil deben ir en `acciones_publicas` para no caer aquí.

Uso:
    class RutVehiculoViewSet(RolMixin, viewsets.ModelViewSet):
        modulo = 'vehiculo'
        acciones_admin = ['create', 'update', 'partial_update', 'destroy']
"""
from rest_framework.permissions import IsAuthenticated

from contenedor.permisos import (
    EsAdminDelContenedor,
    EsMiembroDelContenedor,
    EsMiembroEditor,
    PermisoModuloEditar,
    PermisoModuloVer,
)

ACCIONES_DE_LECTURA = {'list', 'retrieve'}
ACCIONES_DE_ESCRITURA = {'create', 'update', 'partial_update', 'destroy'}


class RolMixin:
    acciones_admin: list = []
    acciones_lectura: list = []
    acciones_publicas: list = []
    modulo: str = None

    def get_permissions(self):
        permisos = [IsAuthenticated()]
        if self.action in (self.acciones_publicas or []):
            return permisos
        if self.action in (self.acciones_admin or []):
            permisos.append(EsAdminDelContenedor())
        elif self.action in ACCIONES_DE_LECTURA or self.action in (self.acciones_lectura or []):
            if self.modulo:
                permisos.append(PermisoModuloVer(self.modulo)())
            else:
                permisos.append(EsMiembroDelContenedor())
        elif self.action in ACCIONES_DE_ESCRITURA:
            if self.modulo:
                permisos.append(PermisoModuloEditar(self.modulo)())
            else:
                permisos.append(EsMiembroEditor())
        else:
            # Acciones @action custom: por defecto requieren editor del modulo si esta definido
            if self.modulo:
                permisos.append(PermisoModuloEditar(self.modulo)())
            else:
                permisos.append(EsMiembroEditor())
        return permisos
