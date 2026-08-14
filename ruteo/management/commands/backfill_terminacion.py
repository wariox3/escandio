"""Crea el Documento de Terminacion de viajes que se cerraron sin el.

Un viaje terminado cuando el backend aun no generaba el snapshot (o por una
falla puntual) queda sin RutTerminacion y su PDF responde "El viaje no tiene
documento de terminacion". Este comando repone el snapshot reusando la MISMA
logica del cierre normal (consolidado_viaje + guardar_terminacion): como un
viaje terminado ya no cambia, el consolidado sigue siendo la foto real.

fecha_cierre queda con la hora del backfill (la hora real del cierre no se
guardo) y usuario_id queda nulo.

Uso:
    python manage.py backfill_terminacion --schema energy --despacho 123
    python manage.py backfill_terminacion --schema energy --despacho 123 --despacho 124
    python manage.py backfill_terminacion --schema energy --todos --dry-run
"""
from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import tenant_context

from contenedor.models import Contenedor
from ruteo.models.despacho import RutDespacho
from ruteo.servicios.despacho import DespachoServicio


class Command(BaseCommand):
    help = ('Crea el snapshot del Documento de Terminacion para viajes ya '
            'terminados que quedaron sin el.')

    def add_arguments(self, parser):
        parser.add_argument('--schema', required=True,
                            help='Contenedor (schema_name) donde estan los viajes.')
        parser.add_argument('--despacho', action='append', type=int, default=[],
                            help='Id del despacho a reponer (repetible).')
        parser.add_argument('--todos', action='store_true',
                            help='Repone TODOS los terminados sin documento del schema.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Muestra que se crearia sin escribir.')

    def handle(self, *args, **options):
        if not options['despacho'] and not options['todos']:
            raise CommandError('Indica --despacho <id> (repetible) o --todos.')

        try:
            contenedor = Contenedor.objects.exclude(schema_name='public').get(
                schema_name=options['schema']
            )
        except Contenedor.DoesNotExist:
            raise CommandError(f"No existe el contenedor '{options['schema']}'.")

        dry = options['dry_run']
        modo = 'DRY-RUN (sin escribir)' if dry else 'aplicando'
        self.stdout.write(f'Backfill de terminacion en {contenedor.schema_name} [{modo}]...')

        # tenant_context (no schema_context) para que connection.tenant sea el
        # Contenedor real y consolidado_viaje resuelva la agencia (= su nombre).
        with tenant_context(contenedor):
            despachos = RutDespacho.objects.filter(
                estado_terminado=True,
                estado_anulado=False,       # anular tambien marca terminado
                terminaciones__isnull=True,
            )
            if options['despacho']:
                despachos = despachos.filter(id__in=options['despacho'])
                encontrados = set(despachos.values_list('id', flat=True))
                for id in options['despacho']:
                    if id not in encontrados:
                        self.stderr.write(self.style.WARNING(
                            f'despacho {id}: omitido (no existe, no esta terminado, '
                            'esta anulado o ya tiene documento)'
                        ))

            creados = 0
            for despacho in despachos.order_by('id'):
                consolidado = DespachoServicio.consolidado_viaje(despacho)
                if not dry:
                    DespachoServicio.guardar_terminacion(despacho, consolidado)
                creados += 1
                self.stdout.write(
                    f"despacho {despacho.id}: OE {consolidado['consecutivo']} "
                    f"placa {consolidado['placa'] or 's/p'} "
                    f"{consolidado['entregadas']}/{consolidado['total_guias']} entregadas, "
                    f"{consolidado['con_novedad']} con novedad"
                )

        self.stdout.write(self.style.SUCCESS(
            f'Fin [{modo}]: {creados} documento(s) de terminacion '
            f'{"por crear" if dry else "creados"}.'
        ))
