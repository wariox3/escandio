"""Recalcula los contadores de VerEntrega (el contador del Home movil) para que
espejen los de RutDespacho (fuente verificada, 0-drift).

VerEntrega (tabla `ver_entrega`, app vertical) se crea al APROBAR el despacho y
NO se actualizaba al entregar -> el Home movil mostraba "0 entregadas" y totales
que no cuadraban con la lista de guias. A partir del fix en
`movil/services/entrega.py` cada entrega la sincroniza; este comando repone las
filas VIEJAS (aprobadas antes del fix o sin mas entregas).

Usa EXACTAMENTE el mismo conteo que `recalcular_contadores_despacho`
(Count('visitas_despacho_rel'...)), no el campo `despacho_id` crudo de RutVisita:
son distintos en despachos liberados/reasignados, y la relacion es la verificada.
Idempotente. NO toca peso/volumen/tiempo. VerEntrega huerfanos (cuyo despacho no
existe) se dejan intactos.

Uso:
    python manage.py recalcular_verentrega            # aplica a todos
    python manage.py recalcular_verentrega --dry-run  # solo muestra
    python manage.py recalcular_verentrega --schema energypruebas
"""
from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django_tenants.utils import schema_context

from contenedor.models import Contenedor
from ruteo.models.despacho import RutDespacho
from vertical.models.entrega import VerEntrega


def recalcular_verentrega(schema_name, dry_run=False):
    """Espeja VerEntrega.visitas/visitas_entregadas del `schema_name` dado sobre
    los contadores verificados de RutDespacho. Devuelve
    {'revisados': int, 'corregidos': [...]}.
    """
    revisados = 0
    corregidos = []
    with schema_context(schema_name):
        # Mismo conteo que recalcular_contadores_despacho (verificado 0-drift).
        despachos = {
            d['id']: (d['_visitas'], d['_entregadas'])
            for d in RutDespacho.objects.annotate(
                _visitas=Count('visitas_despacho_rel'),
                _entregadas=Count(
                    'visitas_despacho_rel',
                    filter=Q(visitas_despacho_rel__estado_entregado=True),
                ),
            ).values('id', '_visitas', '_entregadas')
        }

        por_actualizar = []
        filas = VerEntrega.objects.filter(schema_name=schema_name).only(
            'id', 'despacho_id', 'visitas', 'visitas_entregadas')
        for e in filas.iterator(chunk_size=1000):
            if e.despacho_id not in despachos:
                continue  # VerEntrega huerfano (despacho borrado): no tocar
            revisados += 1
            total, entregadas = despachos[e.despacho_id]
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
    help = ('Espeja VerEntrega.visitas/visitas_entregadas (contador del Home '
            'movil) sobre los contadores verificados de RutDespacho, en todos '
            'los contenedores.')

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
