from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from vertical.models.entrega import VerEntrega
from vertical.serializers.entrega import VerEntregaSerializador

class EntregaViewSet(viewsets.ModelViewSet):
    queryset = VerEntrega.objects.all()
    serializer_class = VerEntregaSerializador
    permission_classes = [permissions.IsAuthenticated]