from django.db import models
from contenedor.models import User
from .conversacion import MsjConversacion


class MsjMensaje(models.Model):
    DIRECCION_ENTRADA = 'in'
    DIRECCION_SALIDA = 'out'
    DIRECCION_CHOICES = [
        (DIRECCION_ENTRADA, 'Entrada'),
        (DIRECCION_SALIDA, 'Salida'),
    ]

    TIPO_TEXTO = 'texto'
    TIPO_IMAGEN = 'imagen'
    TIPO_TEMPLATE = 'template'
    TIPO_AUDIO = 'audio'
    TIPO_DOCUMENTO = 'documento'
    TIPO_UBICACION = 'ubicacion'
    TIPO_CHOICES = [
        (TIPO_TEXTO, 'Texto'),
        (TIPO_IMAGEN, 'Imagen'),
        (TIPO_TEMPLATE, 'Plantilla'),
        (TIPO_AUDIO, 'Audio'),
        (TIPO_DOCUMENTO, 'Documento'),
        (TIPO_UBICACION, 'Ubicación'),
    ]

    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_ENVIADO = 'enviado'
    ESTADO_ENTREGADO = 'entregado'
    ESTADO_LEIDO = 'leido'
    ESTADO_ERROR = 'error'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_ENVIADO, 'Enviado'),
        (ESTADO_ENTREGADO, 'Entregado'),
        (ESTADO_LEIDO, 'Leído'),
        (ESTADO_ERROR, 'Error'),
    ]

    conversacion = models.ForeignKey(MsjConversacion, on_delete=models.CASCADE, related_name='mensajes')
    direccion = models.CharField(max_length=3, choices=DIRECCION_CHOICES)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default=TIPO_TEXTO)
    contenido = models.TextField(null=True, blank=True)
    whatsapp_message_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE)
    error_mensaje = models.TextField(null=True, blank=True)
    media_url = models.TextField(null=True, blank=True)
    media_caption = models.TextField(null=True, blank=True)
    enviado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='mensajes_enviados')
    metadata = models.JSONField(null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "msj_mensaje"
        ordering = ["id"]

    def __str__(self):
        return f'{self.direccion} {self.tipo} {self.estado}'
