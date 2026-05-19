"""Serializers de autenticacion de la API movil v2."""
from decouple import config
from rest_framework import serializers


class UsuarioMovilSerializer(serializers.Serializer):
    """Representacion del usuario para la app movil."""
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    correo = serializers.CharField(read_only=True, allow_null=True)
    nombre = serializers.CharField(read_only=True, allow_null=True)
    apellido = serializers.CharField(read_only=True, allow_null=True)
    nombre_corto = serializers.CharField(read_only=True, allow_null=True)
    telefono = serializers.CharField(read_only=True, allow_null=True)
    numero_identificacion = serializers.CharField(read_only=True, allow_null=True)
    imagen = serializers.SerializerMethodField()
    verificado = serializers.BooleanField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    # Estado de aprobacion del auto-registro: pendiente / aprobado / rechazado.
    estado = serializers.CharField(source='estado_registro', read_only=True)
    # True si el usuario tiene acceso a la app movil en algun contenedor.
    # La app lo usa para mostrar la pantalla de "sin acceso" tras el login.
    acceso_movil = serializers.SerializerMethodField()

    def get_imagen(self, instance) -> str:
        return (
            f"https://{config('DO_BUCKET')}.{config('DO_REGION')}"
            f".digitaloceanspaces.com/{instance.imagen}"
        )

    def get_acceso_movil(self, instance) -> bool:
        if instance.is_superuser:
            return True
        from contenedor.models import Contenedor, UsuarioContenedor
        # Admin de algun contenedor.
        if Contenedor.objects.filter(usuario_id=instance.id).exists():
            return True
        # Miembro con acceso movil en algun contenedor.
        return UsuarioContenedor.objects.filter(
            usuario_id=instance.id, tiene_acceso_movil=True,
        ).exists()


class SesionSerializer(serializers.Serializer):
    """Respuesta de login: tokens estandar + usuario."""
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    usuario = UsuarioMovilSerializer(read_only=True)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})


class RegistroSerializer(serializers.Serializer):
    username = serializers.EmailField()
    password = serializers.CharField(
        write_only=True, min_length=8, style={'input_type': 'password'},
    )
    nombre = serializers.CharField(required=False, allow_blank=True, max_length=255)
    telefono = serializers.CharField(required=False, allow_blank=True, max_length=50)
    # Texto libre: empresa para la que trabaja el conductor. Ayuda al
    # super-admin a saber a que contenedor asignarlo al aprobarlo.
    empresa_nombre = serializers.CharField(
        required=False, allow_blank=True, max_length=255,
    )


class SolicitarClaveSerializer(serializers.Serializer):
    username = serializers.EmailField()
