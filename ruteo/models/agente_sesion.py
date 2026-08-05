from django.db import models

from ruteo.models.despacho import RutDespacho


class RutAgenteSesion(models.Model):
    """Conversacion en curso entre el agente de WhatsApp y un conductor sobre un
    despacho.

    Guarda el `historial` neutral (incluye los turnos de tools) para poder
    RETOMAR el loop cuando llega el siguiente mensaje entrante: el LLM es
    stateless, asi que cada mensaje se procesa con todo el contexto anterior.
    """
    ESTADO_ACTIVA = 'activa'
    ESTADO_CERRADA = 'cerrada'

    despacho = models.ForeignKey(RutDespacho, on_delete=models.CASCADE, related_name='agente_sesiones')
    telefono = models.CharField(max_length=50)
    conductor_nombre = models.CharField(max_length=255, null=True, blank=True)
    estado = models.CharField(max_length=10, default=ESTADO_ACTIVA)
    historial = models.JSONField(default=list)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['telefono', 'estado']),
        ]

    def __str__(self):
        return f'AgenteSesion despacho={self.despacho_id} tel={self.telefono} ({self.estado})'
