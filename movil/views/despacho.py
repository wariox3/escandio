"""Vista de despacho/entrega de la API movil v2."""
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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


class TomarDespachoRequestSerializer(serializers.Serializer):
    """Body de POST /despachos/tomar/: el OE (el numero de Trafico)."""
    oe = serializers.IntegerField(
        min_value=1,
        help_text='El O_E de Trafico (RutDespacho.entrega_id) que el conductor teclea.',
    )


class TomarDespachoView(MovilApiMixin, APIView):
    """El conductor TOMA una orden por su OE (self-service).

    Reemplaza al viejo "cargar por codigo" (que solo leia y guardaba local en el
    dispositivo). Aca, tomar = auto-asignarse: se busca el RutDespacho por
    `entrega_id == oe` en el/los schema(s) del/los contenedor(es) del usuario, se
    setea `conductor_id`, se registra quien la cargo (`cargado_por_id`/`cargado_en`,
    una sola vez) y se propaga `usuario_id` a la VerEntrega PUBLICA para que la
    orden aparezca en "Mis Ordenes" en TODOS los dispositivos del conductor al
    refrescar (no solo en el que la cargo).

    OJO tenant/public: `RutDespacho` es tenant-only (se lee/escribe DENTRO del
    schema_context). `VerEntrega` existe en public Y en cada tenant; el movil lee
    la de PUBLIC, asi que su update va FUERA del schema_context (en el dominio
    base, donde corre esta vista).
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['despachos'],
        request=TomarDespachoRequestSerializer,
        responses=DespachoMovilSerializer,
        examples=[OpenApiExample('Tomar por OE', value={'oe': 1234})],
    )
    def post(self, request, *args, **kwargs):
        from django_tenants.utils import schema_context
        from contenedor.models import Contenedor, UsuarioContenedor
        from ruteo.models.despacho import RutDespacho

        entrada = TomarDespachoRequestSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        oe = entrada.validated_data['oe']

        # Contenedores del usuario con acceso movil (donde puede tomar ordenes).
        # Un superuser podria no tener membresias; en la practica los conductores
        # si las tienen. Se recorre cada schema buscando el OE.
        contenedor_ids = list(
            UsuarioContenedor.objects.filter(
                usuario_id=request.user.id, tiene_acceso_movil=True,
            ).values_list('contenedor_id', flat=True)
        )
        schemas = list(
            Contenedor.objects.filter(id__in=contenedor_ids)
            .values_list('schema_name', flat=True)
        )

        # Fase tenant: hallar el despacho por OE y auto-asignarlo. Se guarda
        # (schema, despacho_id) para actualizar la VerEntrega publica despues.
        encontrado = None  # (schema_name, despacho_id)
        for schema_name in schemas:
            with schema_context(schema_name):
                despacho = (
                    RutDespacho.objects
                    .filter(entrega_id=oe, estado_anulado=False)
                    .first()
                )
                if despacho is None:
                    continue
                despacho.conductor_id = request.user.id
                campos = ['conductor_id']
                if not despacho.cargado_por_id:
                    despacho.cargado_por_id = request.user.id
                    despacho.cargado_en = timezone.now()
                    campos += ['cargado_por_id', 'cargado_en']
                despacho.save(update_fields=campos)
                encontrado = (schema_name, despacho.id)
                break

        if encontrado is None:
            return Response(
                {'codigo': 1, 'titulo': 'No encontrada',
                 'mensaje': f'No hay una orden con OE {oe} en tus contenedores.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Fase public: propagar a la VerEntrega cross-tenant que lee el movil.
        schema_name, despacho_id = encontrado
        ve = VerEntrega.objects.filter(
            despacho_id=despacho_id, schema_name=schema_name,
        ).first()
        if ve is None:
            return Response(
                {'codigo': 2, 'titulo': 'Aun no publicada',
                 'mensaje': 'La orden existe pero todavia no esta publicada al '
                            'movil. Proba de nuevo en unos minutos.'},
                status=status.HTTP_409_CONFLICT,
            )
        if ve.usuario_id != request.user.id:
            ve.usuario_id = request.user.id
            ve.save(update_fields=['usuario_id'])
        return Response(DespachoMovilSerializer(ve).data, status=status.HTTP_200_OK)


class SoltarDespachoRequestSerializer(serializers.Serializer):
    """Body de POST /despachos/soltar/: el id (VerEntrega) de la orden a soltar."""
    id = serializers.IntegerField(
        min_value=1,
        help_text='El id de la orden (VerEntrega.id) que el conductor quiere soltar.',
    )


class SoltarDespachoView(MovilApiMixin, APIView):
    """El conductor SUELTA una orden de su "Mis Ordenes" (inverso de tomar).

    Limpia `usuario_id` de SU VerEntrega (public) y, best-effort, el `conductor_id`
    del RutDespacho (tenant). Scopeado por `usuario_id`: solo puede soltar lo que
    tiene asignado (no toca lo de otros). Resuelve el caso de ordenes huerfanas /
    vacias que no tienen despacho en Trafico y por eso no se podian desasignar.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['despachos'],
        request=SoltarDespachoRequestSerializer,
        responses={200: OpenApiResponse(description='Orden soltada')},
        examples=[OpenApiExample('Soltar orden', value={'id': 14163})],
    )
    def post(self, request, *args, **kwargs):
        entrada = SoltarDespachoRequestSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        ve_id = entrada.validated_data['id']

        ve = VerEntrega.objects.filter(
            pk=ve_id, usuario_id=request.user.id,
        ).first()
        if ve is None:
            return Response(
                {'codigo': 1, 'titulo': 'No encontrada',
                 'mensaje': 'Esa orden no esta asignada a vos.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        schema_name = ve.schema_name
        despacho_id = ve.despacho_id
        ve.usuario_id = None
        ve.save(update_fields=['usuario_id'])
        # Best-effort: limpiar tambien el conductor en el tenant (si el despacho
        # existe). Fail-silent: la orden ya se solto de Mis Ordenes (lo que ve el
        # conductor); si el despacho es huerfano/inexistente, no pasa nada.
        if schema_name and despacho_id:
            from django_tenants.utils import schema_context
            from ruteo.models.despacho import RutDespacho
            try:
                with schema_context(schema_name):
                    RutDespacho.objects.filter(
                        pk=despacho_id, conductor_id=request.user.id,
                    ).update(conductor_id=None)
            except Exception:
                pass
        return Response({'mensaje': 'Soltaste la orden'}, status=status.HTTP_200_OK)
