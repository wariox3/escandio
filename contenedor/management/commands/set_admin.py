from django.core.management.base import BaseCommand
from contenedor.models import User


class Command(BaseCommand):
    help = 'Marca un usuario como administrador (is_staff=True)'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str)

    def handle(self, *args, **options):
        email = options['email']
        try:
            user = User.objects.get(username=email)
            user.is_staff = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f'{email} marcado como admin'))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Usuario {email} no encontrado'))
