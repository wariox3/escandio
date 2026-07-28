"""Recalcula los contadores de visitas de cada despacho desde las visitas reales.

Los campos denormalizados del despacho (visitas, visitas_entregadas,
visitas_novedad) se desincronizan con las visitas reales: llegaban a dar
asignadas < entregadas y a no cuadrar con el informe de zonas. Este comando los
repone contando las visitas de verdad.

NO toca visitas_liberadas (cuenta visitas ya desvinculadas, no es recomputable)
ni los sumatorios (peso/volumen/tiempo).

Uso:
    python manage.py recalcular_contadores_despacho            # aplica a todos
    python manage.py recalcular_contadores_despacho --dry-run  # solo muestra
    python manage.py recalcular_contadores_despacho --schema energy
"""
from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django_tenants.utils import schema_context

from contenedor.models import Contenedor
from ruteo.models.despacho import RutDespacho


def recalcular_contadores(dry_run=False):
    """Recalcula los contadores de despacho del schema ACTUAL desde las visitas.

    Devuelve {'revisados': int, 'corregidos': [{'id', 'antes', 'despues'}]}.
    """
    despachos = RutDespacho.objects.annotate(
        _asignadas=Count('visitas_despacho_rel'),
        _entregadas=Count('visitas_despacho_rel', filter=Q(visitas_despacho_rel__estado_entregado=True)),
        _novedades=Count('visitas_despacho_rel', filter=Q(visitas_despacho_rel__estado_novedad=True)),
    ).only('id', 'visitas', 'visitas_entregadas', 'visitas_novedad')

    revisados = 0
    corregidos = []
    por_actualizar = []
    for d in despachos.iterator(chunk_size=1000):
        revisados += 1
        if (d.visitas != d._asignadas
                or d.visitas_entregadas != d._entregadas
                or d.visitas_novedad != d._novedades):
            corregidos.append({
                'id': d.id,
                'antes': {'visitas': d.visitas, 'entregadas': d.visitas_entregadas, 'novedad': d.visitas_novedad},
                'despues': {'visitas': d._asignadas, 'entregadas': d._entregadas, 'novedad': d._novedades},
            })
            d.visitas = d._asignadas
            d.visitas_entregadas = d._entregadas
            d.visitas_novedad = d._novedades
            por_actualizar.append(d)

    if por_actualizar and not dry_run:
        RutDespacho.objects.bulk_update(
            por_actualizar,
            ['visitas', 'visitas_entregadas', 'visitas_novedad'],
            batch_size=500,
        )
    return {'revisados': revisados, 'corregidos': corregidos}


class Command(BaseCommand):
    help = ('Recalcula visitas/visitas_entregadas/visitas_novedad de cada despacho '
            'desde las visitas reales, en todos los contenedores.')

    def add_arguments(self, parser):
        parser.add_argument('--schema', help='Procesa solo el contenedor indicado (schema_name).')
        parser.add_argument('--dry-run', action='store_true', help='Muestra los cambios sin escribir.')

    def handle(self, *args, **options):
        contenedores = Contenedor.objects.exclude(schema_name='public')
        if options.get('schema'):
            contenedores = contenedores.filter(schema_name=options['schema'])

        dry = options['dry_run']
        modo = 'DRY-RUN (sin escribir)' if dry else 'aplicando'
        self.stdout.write(f'Recalculando contadores de despacho [{modo}]...')

        total_revisados = 0
        total_corregidos = 0
        for contenedor in contenedores.order_by('schema_name'):
            try:
                with schema_context(contenedor.schema_name):
                    resultado = recalcular_contadores(dry_run=dry)
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'{contenedor.schema_name}: ERROR - {e}'))
                continue

            total_revisados += resultado['revisados']
            total_corregidos += len(resultado['corregidos'])
            if resultado['corregidos']:
                self.stdout.write(
                    f"{contenedor.schema_name}: {len(resultado['corregidos'])} corregidos "
                    f"de {resultado['revisados']} revisados"
                )
                for c in resultado['corregidos']:
                    a, d = c['antes'], c['despues']
                    self.stdout.write(
                        f"  despacho {c['id']}: "
                        f"visitas {a['visitas']:g}->{d['visitas']} "
                        f"entregadas {a['entregadas']:g}->{d['entregadas']} "
                        f"novedad {a['novedad']:g}->{d['novedad']}"
                    )

        self.stdout.write(self.style.SUCCESS(
            f'Fin [{modo}]: {total_revisados} despachos revisados, {total_corregidos} corregidos.'
        ))
