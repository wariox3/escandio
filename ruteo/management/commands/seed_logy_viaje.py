"""Crea un viaje de PRUEBA para LOGY, desde cero, en un contenedor.

Arma un vehículo + un despacho aprobado con fecha de HOY + N guías pendientes,
listo para probar el asistente de WhatsApp sin depender de data vieja ni del
flujo de ruteo. Los contadores del despacho los mantiene la señal (no se tocan
a mano). Es idempotente en el vehículo (reusa la placa si ya existe).

Uso:
    python manage.py seed_logy_viaje --contenedor energy --telefono 573006134088
    python manage.py seed_logy_viaje --contenedor "energy pruebas" --placa LOGY01 --guias 4
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django_tenants.utils import schema_context

from contenedor.models import Contenedor

# (destinatario, dirección, teléfono) de ejemplo para las guías.
_GUIAS_MUESTRA = [
    ('Ana Ruiz', 'CL 10 #5-20, Medellín', '3001112233'),
    ('Juan Pérez', 'CR 43 #22-15, Envigado', '3004445566'),
    ('María Gómez', 'DG 30 #8-40, Itagüí', '3007778899'),
    ('Luis Torres', 'CL 50 #12-30, Bello', '3002223344'),
    ('Sara Díaz', 'CR 65 #40-10, Medellín', '3005556677'),
]


def crear_viaje_prueba(placa='LOGY01', telefono='', n_guias=3):
    """Crea (en el schema ACTUAL) un vehículo + despacho aprobado HOY + N guías
    pendientes. Devuelve el despacho. Los contadores los mantiene la señal."""
    from ruteo.models.despacho import RutDespacho
    from ruteo.models.vehiculo import RutVehiculo
    from ruteo.models.visita import RutVisita

    placa = (placa or 'LOGY01').upper().strip()
    n_guias = max(1, min(int(n_guias or 3), len(_GUIAS_MUESTRA)))

    vehiculo, _ = RutVehiculo.objects.get_or_create(
        placa=placa, defaults={'estado_asignado': True})
    despacho = RutDespacho.objects.create(
        estado_aprobado=True, estado_anulado=False, estado_terminado=False,
        fecha=timezone.now(), vehiculo=vehiculo,
        conductor_telefono=(telefono or None))
    for i in range(n_guias):
        nombre, direccion, tel = _GUIAS_MUESTRA[i]
        RutVisita.objects.create(
            despacho=despacho, ciudad_id=None,
            numero=str(900000 + despacho.id * 10 + i),
            destinatario=nombre, destinatario_direccion=direccion,
            destinatario_telefono=tel, orden=i + 1,
            estado_entregado=False, estado_novedad=False)
    return despacho


class Command(BaseCommand):
    help = ('Crea un viaje de prueba para LOGY (vehículo + despacho aprobado hoy + '
            'guías pendientes) en un contenedor.')

    def add_arguments(self, parser):
        parser.add_argument('--contenedor', required=True,
                            help='schema_name o nombre del contenedor (ej. energy o "energy pruebas").')
        parser.add_argument('--telefono', default='',
                            help='Teléfono autorizado (ej. 573006134088) para que "hola" abra el menú.')
        parser.add_argument('--placa', default='LOGY01')
        parser.add_argument('--guias', type=int, default=3)

    def handle(self, *args, **opts):
        ref = opts['contenedor']
        cont = (Contenedor.objects.filter(schema_name=ref).first()
                or Contenedor.objects.filter(nombre__iexact=ref).first()
                or Contenedor.objects.filter(nombre__icontains=ref).first())
        if not cont:
            disponibles = ', '.join(
                Contenedor.objects.exclude(schema_name='public')
                .values_list('schema_name', flat=True)[:30])
            raise CommandError(f'No encontré el contenedor "{ref}". Disponibles: {disponibles}')

        with schema_context(cont.schema_name):
            despacho = crear_viaje_prueba(opts['placa'], opts['telefono'], opts['guias'])
            did, placa, n = despacho.id, despacho.vehiculo.placa, despacho.visitas_despacho_rel.count()

        self.stdout.write(self.style.SUCCESS(f'✅ Viaje de prueba creado en "{cont.schema_name}":'))
        self.stdout.write(f'   Despacho #{did} · placa {placa} · {n} guías pendientes')
        self.stdout.write(f'   Autorizado: {opts["telefono"] or "(cualquiera con la placa)"}')
        self.stdout.write('')
        self.stdout.write('   Probá por WhatsApp:')
        if opts['telefono']:
            self.stdout.write(f'     • "hola" desde {opts["telefono"]}  → menú directo')
        self.stdout.write(f'     • "{placa}"  → arranca el menú')
