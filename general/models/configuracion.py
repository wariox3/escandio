from django.db import models
from general.models.empresa import GenEmpresa

class GenConfiguracion(models.Model):   
    id = models.BigIntegerField(primary_key=True)         
    informacion_factura = models.TextField(null=True)
    informacion_factura_superior = models.TextField(null=True)
    gen_uvt = models.DecimalField(max_digits=20, decimal_places=6, default=49799)
    gen_emitir_automaticamente = models.BooleanField(default = False)
    empresa = models.ForeignKey(GenEmpresa, on_delete=models.PROTECT, default=1)    
    rut_sincronizar_complemento = models.BooleanField(default = False)
    rut_decodificar_direcciones = models.BooleanField(default = True)
    rut_rutear_franja = models.BooleanField(default = False)
    rut_direccion_origen = models.TextField(null=True)
    rut_latitud = models.DecimalField(max_digits=25, decimal_places=15, null=True)
    rut_longitud = models.DecimalField(max_digits=25, decimal_places=15, null=True)
    rut_hora_inicio = models.TimeField(null=True, default='07:00')
    rut_cita_tipo_defecto = models.CharField(max_length=20, choices=[('obligatoria', 'Obligatoria'), ('preferente', 'Preferente')], default='obligatoria')
    rut_whatsapp_habilitado = models.BooleanField(default=False)
    rut_estrategia_ruteo = models.CharField(max_length=20, choices=[
        ('distancia', 'Ruta más corta'),
        ('tiempo', 'Menor tiempo'),
        ('balanceado', 'Balanceado'),
    ], default='balanceado')
    rut_alerta_parada_activa = models.BooleanField(default=False)
    rut_alerta_parada_minutos = models.IntegerField(default=15)
    rut_alerta_parada_radio_metros = models.IntegerField(default=80)
    rut_alerta_geocerca_activa = models.BooleanField(default=False)
    tte_usuario_rndc = models.CharField(max_length=50, null=True)
    tte_clave_rndc = models.CharField(max_length=50, null=True)
    tte_numero_poliza = models.CharField(max_length=50, null=True)
    tte_fecha_vence_poliza = models.DateField(null=True)
    tte_numero_identificacion_aseguradora = models.CharField(max_length=50, null=True)
    class Meta:
        db_table = "gen_configuracion"
        ordering = ["-id"]