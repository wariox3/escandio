from django.db import models
from django_tenants.models import TenantMixin, DomainMixin
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser, PermissionsMixin

class UserManager(BaseUserManager):
    def _create_user(self, username, correo, nombre, apellido, numero_identificacion, password, is_staff, is_superuser, **extra_fields):
        user = self.model(
            username = username,
            correo = correo,
            nombre = nombre,
            apellido = apellido,
            numero_identificacion = numero_identificacion,
            is_staff = is_staff,
            is_superuser = is_superuser,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self.db)
        return user

    def create_user(self, username, correo, nombre, apellido, password=None, **extra_fields):
        return self._create_user(username, correo, nombre, apellido, password, False, False, **extra_fields)

    def create_superuser(self, username, correo, nombre, apellido, password=None, **extra_fields):
        return self._create_user(username, correo, nombre, apellido, password, True, True, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    username = models.EmailField(max_length = 255, unique = True)
    correo = models.EmailField(max_length = 255, unique = True)
    nombre = models.CharField(max_length = 255, null = True)
    apellido = models.CharField(max_length = 255, null = True)
    nombre_corto = models.CharField(max_length = 255, null = True)
    numero_identificacion = models.CharField(max_length=20, null = True)
    empresa_nombre = models.CharField(max_length = 255, null = True)
    empresa_numero_identificacion = models.CharField(max_length=20, null = True)    
    cargo = models.CharField(max_length=255, null = True)
    telefono = models.CharField(max_length = 50, null = True)
    idioma = models.CharField(max_length = 2, default='es')
    imagen = models.TextField(null=True)
    imagen_thumbnail = models.TextField(null=True)
    vr_saldo = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    vr_credito = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    vr_abono = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    fecha_limite_pago = models.DateField(null=True)
    is_active = models.BooleanField(default = True)
    is_staff = models.BooleanField(default = False)
    verificado = models.BooleanField(default = False)
    cortesia = models.BooleanField(default = False)
    es_socio = models.BooleanField(default = False)
    es_administrador = models.BooleanField(default = False)
    socio_id = models.IntegerField(null = True)
    operacion_id = models.IntegerField(null = True)
    operacion_cargo_id = models.IntegerField(null = True)
    fecha_creacion = models.DateTimeField(null=True, auto_now_add=True)
    aplicacion = models.CharField(max_length=10, null=True)
    dominio = models.CharField(max_length = 50, null=True)
    objects = UserManager()

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['correo','nombre','apellido']

    def __str__(self):
        return f'{self.nombre} {self.apellido}' 

class Contenedor(TenantMixin):
    schema_name = models.CharField(max_length=100)
    nombre = models.CharField(max_length=200, null=True)    
    fecha = models.DateTimeField(auto_now_add=True)
    fecha_ultima_conexion = models.DateTimeField(auto_now_add=True, null=True)
    imagen = models.TextField(null=True)    
    usuarios = models.IntegerField(default=1)         
    auto_create_schema = True
    auto_drop_schema = True

    def __str__(self):
        return self.schema_name
    
    class Meta:
        db_table = "ctn_contenedor"

class Dominio(DomainMixin):
    pass

    class Meta:
        db_table = "ctn_dominio"

class CtnPais(models.Model):
    id = models.CharField(primary_key=True, max_length=2)
    nombre = models.CharField(max_length=50, null=True)
    codigo = models.CharField(max_length=10, null=True)
    
    class Meta:
        db_table = "ctn_pais"

class CtnEstado(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=50)
    codigo = models.CharField(max_length=10, null=True)
    pais = models.ForeignKey(CtnPais, on_delete=models.CASCADE)

    class Meta:
        db_table = "ctn_estado"

class CtnCiudad(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=50) 
    latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True)
    codigo_postal = models.CharField(max_length=10, null=True)
    porcentaje_impuesto = models.DecimalField(max_digits=5, decimal_places=2, default=0)  
    estado = models.ForeignKey(CtnEstado, on_delete=models.CASCADE)
    
    class Meta:
        db_table = "ctn_ciudad"      
        
class UsuarioContenedor(models.Model):
    rol = models.CharField(max_length=20, null=True)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    contenedor = models.ForeignKey(Contenedor, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ('usuario', 'contenedor')
        db_table = "ctn_usuario_contenedor"                      

class CtnDireccion(models.Model):
    fecha = models.DateTimeField()
    direccion = models.CharField(max_length=200)
    direccion_formato = models.CharField(max_length=200)    
    latitud = models.DecimalField(max_digits=25, decimal_places=15, null=True)
    longitud = models.DecimalField(max_digits=25, decimal_places=15, null=True)
    cantidad_resultados = models.IntegerField(default=0)
    resultados = models.JSONField(null=True, blank=True)
    ciudad = models.ForeignKey(CtnCiudad, on_delete=models.PROTECT, null=True)
    
    class Meta:
        db_table = "ctn_direccion"

class CtnVerificacion(models.Model):
    usuario_id = models.IntegerField(null=True)
    contenedor_id = models.IntegerField(null=True)
    token = models.CharField(max_length=50)
    estado_usado = models.BooleanField(default = False)
    vence = models.DateField(null=True)
    accion = models.CharField(max_length=10, default='registro')
    usuario_invitado_username = models.EmailField(max_length = 255, null=True)

    class Meta:
        db_table = "ctn_verificacion"         