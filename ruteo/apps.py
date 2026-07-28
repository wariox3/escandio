from django.apps import AppConfig


class RuteoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ruteo'

    def ready(self):
        from . import signals  # noqa: F401  (registra las señales de contadores)
