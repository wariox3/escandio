from django.db import models

from ruteo.models.despacho import RutDespacho


class RutAgenteSesion(models.Model):
    """Conversacion en curso entre el agente (LOGY) y un conductor sobre un despacho.

    El flujo es una MAQUINA DE ESTADOS determinística: `paso` es el estado actual
    (menu, guia, tipo, motivo, confirma, otra) y `contexto` guarda el borrador de la
    novedad en curso (guía y tipo elegidos, motivo, y las ya registradas). El
    `historial` queda como transcripción legible para el inbox/depuración.
    """
    ESTADO_ACTIVA = 'activa'
    ESTADO_CERRADA = 'cerrada'

    # Pasos de la máquina de estados del flujo de novedades.
    PASO_MENU = 'menu'
    PASO_GUIA = 'guia'
    PASO_TIPO = 'tipo'
    PASO_MOTIVO = 'motivo'
    PASO_CONFIRMA = 'confirma'
    PASO_OTRA = 'otra'

    despacho = models.ForeignKey(RutDespacho, on_delete=models.CASCADE, related_name='agente_sesiones')
    telefono = models.CharField(max_length=50)
    conductor_nombre = models.CharField(max_length=255, null=True, blank=True)
    estado = models.CharField(max_length=10, default=ESTADO_ACTIVA)
    paso = models.CharField(max_length=20, default=PASO_MENU)
    contexto = models.JSONField(default=dict)
    historial = models.JSONField(default=list)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['telefono', 'estado']),
        ]

    def __str__(self):
        return f'AgenteSesion despacho={self.despacho_id} tel={self.telefono} ({self.estado})'
