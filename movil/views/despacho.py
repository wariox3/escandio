"""Vista de despacho/entrega de la API movil v2."""
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from movil.serializers.despacho import DespachoMovilSerializer
from movil.views.base import MovilApiMixin
from vertical.models.entrega import VerEntrega


class DespachoMovilView(MovilApiMixin, generics.RetrieveAPIView):
    """Resuelve un codigo de despacho a su resumen + tenant (schema_name).

    Es el endpoint de arranque: corre en el dominio base (no en un subdominio
    de tenant) porque la app todavia no sabe a que tenant pertenece el codigo.
    Por eso basta IsAuthenticated, no EsConductorMovil.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = DespachoMovilSerializer
    queryset = VerEntrega.objects.all()

    def get_queryset(self):
        # Scope del despacho que puede resolver el usuario:
        # - admin del contenedor / coordinador movil -> todos los despachos
        #   del contenedor.
        # - conductor -> solo los asignados a el (VerEntrega.usuario_id) o aun
        #   sin asignar (usuario_id NULL): no rompe despachos/datos previos.
        # Un despacho fuera del scope -> 404.
        user = self.request.user
        if user.is_superuser:
            return VerEntrega.objects.all()
        from contenedor.models import Contenedor, UsuarioContenedor
        ids_acceso_total = set(Contenedor.objects.filter(
            usuario_id=user.id,
        ).values_list('id', flat=True))
        ids_conductor = set()
        membresias = UsuarioContenedor.objects.filter(
            usuario_id=user.id, tiene_acceso_movil=True,
        ).values_list('contenedor_id', 'perfil_movil')
        for contenedor_id, perfil_movil in membresias:
            if perfil_movil == 'conductor':
                ids_conductor.add(contenedor_id)
            else:
                # coordinador (o sin perfil definido) ve todo el contenedor.
                ids_acceso_total.add(contenedor_id)
        # Ser admin/coordinador de un contenedor manda sobre el rol conductor.
        ids_conductor -= ids_acceso_total
        return VerEntrega.objects.filter(
            Q(contenedor_id__in=ids_acceso_total)
            | (
                Q(contenedor_id__in=ids_conductor)
                & (Q(usuario_id=user.id) | Q(usuario_id__isnull=True))
            )
        )

    @extend_schema(tags=['despachos'])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class DespachosMiasView(MovilApiMixin, generics.ListAPIView):
    """Lista los despachos asignados al conductor autenticado.

    Filtra VerEntrega por usuario_id == request.user.id, ordenados por fecha
    descendente. Devuelve un array plano (sin paginar): un conductor maneja
    pocos despachos vigentes a la vez, no vale la pena paginar.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = DespachoMovilSerializer
    pagination_class = None

    def get_queryset(self):
        return VerEntrega.objects.filter(
            usuario_id=self.request.user.id,
        ).order_by('-fecha', '-id')

    @extend_schema(tags=['despachos'])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
