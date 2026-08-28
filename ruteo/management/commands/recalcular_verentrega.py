"""Recalcula los contadores de VerEntrega (el contador del Home movil) desde las
visitas reales de cada despacho.

VerEntrega (tabla `ver_entrega`, app vertical) se crea al APROBAR el despacho y
NO se actualizaba al entregar -> el Home movil mostraba "0 entregadas" y totales
que no cuadraban con la lista de guias. A partir del fix en
`movil/services/entrega.py` cada entrega la sincroniza; este comando repone las
filas VIEJAS (despachos aprobados antes del fix, o que ya no tendran mas
entregas y por eso no se auto-corrigen).

Recalcula ABSOLUTO desde RutVisita (idempotente). NO toca peso/volumen/tiempo.

Uso:
    python manage.py recalcular_verentrega            # aplica a todos
    python manage.py recalcular_verentrega --dry-run  # solo muestra
    python manage.py recalcular_verentrega --schema energy
"""
from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django_tenants.utils import schema_context

from contenedor.models import Contenedor
from ruteo.models.visita import RutVisita
from vertical.models.entrega import VerEntrega


def recalcular_verentrega(schema_name, dry_run=False):
    """Repone VerEntrega.visitas/visitas_entregadas del `schema_name` dado desde
    las RutVisita reales. Devuelve {'revisados': int, 'corregidos': [...]}.

    Se hace todo dentro del schema_context del tenant: sirve tanto si ver_entrega
    es una tabla compartida (public, accesible desde el tenant) como si fuera por
    schema. Se filtra por schema_name para acotar en el caso compartido.
    """
    revisados = 0
    corregidos = []
    with schema_context(schema_name):
        # Conteo real por despacho desde las visitas del tenant.
        conteos = {
            r['despacho_id']: (r['total'], r['entregadas'])
            for r in RutVisita.objects
            .filter(despacho_id__isnull=False)
            .values('despacho_id')
            .annotate(
                total=Count('id'),
                entregadas=Count('id', filter=Q(estado_entregado=True)),
            )
        }

        por_actualizar = []
        filas = VerEntrega.objects.filter(schema_name=schema_name).only(
            'id', 'despacho_id', 'visitas', 'visitas_entregadas')
        for e in filas.iterator(chunk_size=1000):
            revisados += 1
            total, entregadas = conteos.get(e.despacho_id, (0, 0))
            if e.visitas != total or e.visitas_entregadas != entregadas:
                corregidos.append({
                    'id': e.id,
                    'despacho_id': e.despacho_id,
                    'antes': {'visitas': e.visitas, 'entregadas': e.visitas_entregadas},
                    'despues': {'visitas': total, 'entregadas': entregadas},
                })
                e.visitas = total
                e.visitas_entregadas = entregadas
                por_actualizar.append(e)

        if por_actualizar and not dry_run:
            VerEntrega.objects.bulk_update(
                por_actualizar, ['visitas', 'visitas_entregadas'], batch_size=500)

    return {'revisados': revisados, 'corregidos': corregidos}


class Command(BaseCommand):
    help = ('Recalcula VerEntrega.visitas/visitas_entregadas (contador del Home '
            'movil) desde las visitas reales, en todos los contenedores.')

    def add_arguments(self, parser):
        parser.add_argument('--schema', help='Procesa solo el contenedor indicado (schema_name).')
        parser.add_argument('--dry-run', action='store_true', help='Muestra los cambios sin escribir.')

    def handle(self, *args, **options):
        contenedores = Contenedor.objects.exclude(schema_name='public')
        if options.get('schema'):
            contenedores = contenedores.filter(schema_name=options['schema'])

        dry = options['dry_run']
        modo = 'DRY-RUN (sin escribir)' if dry else 'aplicando'
        self.stdout.write(f'Recalculando VerEntrega (contador Home) [{modo}]...')

        total_revisados = 0
        total_corregidos = 0
        for contenedor in contenedores.order_by('schema_name'):
            try:
                resultado = recalcular_verentrega(contenedor.schema_name, dry_run=dry)
            except Exception as e:  # noqa: BLE001
                self.stderr.write(self.style.ERROR(f'{contenedor.schema_name}: ERROR - {e}'))
                continue

            total_revisados += resultado['revisados']
            total_corregidos += len(resultado['corregidos'])
            if resultado['corregidos']:
                self.stdout.write(
                    f"{contenedor.schema_name}: {len(resultado['corregidos'])} corregidas "
                    f"de {resultado['revisados']} revisadas"
                )
                for c in resultado['corregidos']:
                    a, d = c['antes'], c['despues']
                    self.stdout.write(
                        f"  VerEntrega {c['id']} (despacho {c['despacho_id']}): "
                        f"visitas {a['visitas']:g}->{d['visitas']} "
                        f"entregadas {a['entregadas']:g}->{d['entregadas']}"
                    )

        self.stdout.write(self.style.SUCCESS(
            f'Fin [{modo}]: {total_revisados} filas revisadas, {total_corregidos} corregidas.'
        ))
