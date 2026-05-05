from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from vertical.models.entrega import VerEntrega
from vertical.serializers.entrega import VerEntregaSerializador

class EntregaViewSet(viewsets.ModelViewSet):
    # RETROCOMPAT MOVIL v1.6.4 - ver contenedor/contrato_movil.py
    # GET /vertical/entrega/{codigo}/ debe seguir aceptando IsAuthenticated.
    # Si se aplica RolMixin, retrieve/list deben permanecer en acciones_publicas.
    queryset = VerEntrega.objects.all()
    serializer_class = VerEntregaSerializador
    permission_classes = [permissions.IsAuthenticated]