from django.db import models
from ruteo.models.despacho import RutDespacho


class RutTerminacion(models.Model):
    """Snapshot INMUTABLE del cierre de un viaje (Documento de Terminacion).

    Se crea al confirmar TERMINAR. Guarda el encabezado y el resumen CONGELADOS
    (denormalizados) para que el documento no cambie si luego se edita el
    despacho, se resuelve una novedad o cambia un catalogo. El PDF se regenera
    determinísticamente desde estas filas (no se almacenan bytes del PDF).
    """
    despacho = models.ForeignKey(RutDespacho, on_delete=models.PROTECT, related_name='terminaciones')
    # Numeracion propia del documento. Politica pendiente de definir (funcional):
    # queda opcional para no bloquear el desarrollo.
    consecutivo = models.IntegerField(null=True, blank=True)
    fecha_cierre = models.DateTimeField()
    usuario_id = models.IntegerField(null=True)
    # --- encabezado congelado ---
    placa = models.CharField(max_length=20, null=True)
    conductor_nombre = models.CharField(max_length=255, null=True)
    fecha_viaje = models.DateTimeField(null=True)
    fecha_salida = models.DateTimeField(null=True)
    # --- resumen congelado ---
    total_guias = models.IntegerField(default=0)
    entregadas = models.IntegerField(default=0)
    con_novedad = models.IntegerField(default=0)
    porcentaje = models.DecimalField(max_digits=5, decimal_places=1, default=0)

    class Meta:
        db_table = "rut_terminacion"
        ordering = ["-id"]


class RutTerminacionNovedad(models.Model):
    """Detalle congelado: una fila por guia que FINALIZO con novedad."""
    terminacion = models.ForeignKey(RutTerminacion, on_delete=models.CASCADE, related_name='novedades')
    numero = models.IntegerField(null=True)
    destinatario = models.CharField(max_length=150, null=True)
    tipo_novedad = models.CharField(max_length=60, null=True)
    descripcion = models.CharField(max_length=255, null=True)
    fecha = models.DateTimeField(null=True)

    class Meta:
        db_table = "rut_terminacion_novedad"
        ordering = ["id"]
