"""Crea o actualiza un super admin del schema public.

Uso:
    python manage.py crear_super_admin --email=admin@ruteo.co \
        --nombre=Admin --apellido=Ruteo

Flags:
    --exclusivo     Revoca is_superuser/is_staff de los demás usuarios.
    --password      Si se omite, lo pide por stdin sin mostrarlo (getpass).

Existe porque el manager por defecto de User tiene un bug en la firma
(create_user pasa password en la posición de numero_identificacion),
así que createsuperuser de Django no funciona aquí.
"""

import getpass
import sys

from django.core.management.base import BaseCommand, CommandError

from contenedor.models import User


class Command(BaseCommand):
    help = 'Crea (o actualiza) un super admin del schema public.'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, required=True,
                            help='Email que se usará como username y correo.')
        parser.add_argument('--nombre', type=str, default='Admin')
        parser.add_argument('--apellido', type=str, default='Ruteo')
        parser.add_argument('--password', type=str, default=None,
                            help='Si se omite, se pide por stdin sin echo.')
        parser.add_argument('--exclusivo', action='store_true',
                            help='Revoca super/staff de los demás usuarios.')

    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        nombre = options['nombre']
        apellido = options['apellido']
        password = options['password']
        exclusivo = options['exclusivo']

        if not password:
            password = getpass.getpass('Password para el super admin: ')
            password_check = getpass.getpass('Confirmar password: ')
            if password != password_check:
                raise CommandError('Las contraseñas no coinciden.')
        if len(password) < 8:
            raise CommandError('Password muy corta (mínimo 8 caracteres).')

        self.stdout.write(self.style.NOTICE('--- Superusers actuales ---'))
        for u in User.objects.filter(is_superuser=True):
            self.stdout.write(
                f'  id={u.id} username={u.username} '
                f'is_staff={u.is_staff} is_active={u.is_active}'
            )

        nuevo = User.objects.filter(username=email).first()
        if nuevo:
            self.stdout.write(self.style.WARNING(
                f'Ya existe {email} — actualizando flags y password'
            ))
            nuevo.is_staff = True
            nuevo.is_superuser = True
            nuevo.is_active = True
            nuevo.set_password(password)
            nuevo.save()
        else:
            nuevo = User(
                username=email,
                correo=email,
                nombre=nombre,
                apellido=apellido,
                is_staff=True,
                is_superuser=True,
                is_active=True,
                verificado=True,
            )
            nuevo.set_password(password)
            nuevo.save()
            self.stdout.write(self.style.SUCCESS(
                f'Creado {email} id={nuevo.id}'
            ))

        if exclusivo:
            otros = User.objects.filter(
                is_superuser=True
            ).exclude(id=nuevo.id)
            cant = otros.count()
            self.stdout.write(self.style.NOTICE(
                f'--- Revocando super/staff de {cant} usuario(s) ---'
            ))
            for u in otros:
                self.stdout.write(f'  revocando {u.username} (id={u.id})')
            otros.update(is_superuser=False, is_staff=False)

        self.stdout.write(self.style.NOTICE('--- Superusers después ---'))
        for u in User.objects.filter(is_superuser=True):
            self.stdout.write(
                f'  id={u.id} username={u.username} is_active={u.is_active}'
            )
