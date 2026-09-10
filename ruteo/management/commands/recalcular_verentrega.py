"""Recalcula los contadores de VerEntrega (el contador del Home movil) para que
espejen los de RutDespacho (fuente verificada, 0-drift).

VerEntrega (tabla `ver_entrega`, app vertical) se crea al APROBAR el despacho y
NO se actualizaba al entregar -> el Home movil mostraba "0 entregadas" y totales
que no cuadraban con la lista de guias. A partir del fix en
`movil/services/entrega.py` cada entrega la sincroniza; este comando repone las
filas VIEJAS (aprobadas antes del fix o sin mas entregas).

Espeja los CAMPOS ALMACENADOS de RutDespacho (visitas / visitas_entregadas), que
son el snapshot que mantiene la señal/`recalcular_contadores_despacho` y el que se
muestra en el Home — NO el count vivo de la relacion, que difiere en despachos
liberados/reasignados (ej. despacho 62: campo=12 vs count vivo=0). Idempotente.
NO toca peso/volumen/tiempo. VerEntrega huerfanos (cuyo despacho no existe) se
dejan intactos.

Uso:
    python manage.py recalcular_verentrega            # aplica a todos
    python manage.py recalcular_verentrega --dry-run  # solo muestra
    python manage.py recalcular_verentrega --schema energypruebas
"""
from django.core.management.base import BaseCommand
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
        # Espeja los CAMPOS ALMACENADOS de RutDespacho (el snapshot que se quiere
        # mostrar en el Home), NO el count vivo de la relacion (que difiere en
        # despachos liberados/reasignados).
        despachos = {
            d['id']: (d['visitas'], d['visitas_entregadas'], d['codigo_complemento'])
            for d in RutDespacho.objects.values(
                'id', 'visitas', 'visitas_entregadas', 'codigo_complemento')
        }

        por_actualizar = []
        filas = VerEntrega.objects.filter(schema_name=schema_name).only(
            'id', 'despacho_id', 'visitas', 'visitas_entregadas',
            'codigo_complemento')
        for e in filas.iterator(chunk_size=1000):
            if e.despacho_id not in despachos:
                continue  # VerEntrega huerfano (despacho borrado): no tocar
            revisados += 1
            total, entregadas, codigo = despachos[e.despacho_id]
            necesita_update = False
            if e.visitas != total or e.visitas_entregadas != entregadas:
                corregidos.append({
                    'id': e.id,
                    'despacho_id': e.despacho_id,
                    'antes': {'visitas': e.visitas, 'entregadas': e.visitas_entregadas},
                    'despues': {'visitas': total, 'entregadas': entregadas},
                })
                e.visitas = total
                e.visitas_entregadas = entregadas
                necesita_update = True
            # Backfill del codigo del complemento (identificador del Home). No se
            # cuenta como "corregida" (eso es solo para los contadores) pero se
            # persiste igual para las filas viejas creadas antes de este campo.
            if e.codigo_complemento != codigo:
                e.codigo_complemento = codigo
                necesita_update = True
            if necesita_update:
                por_actualizar.append(e)

        if por_actualizar and not dry_run:
            VerEntrega.objects.bulk_update(
                por_actualizar,
                ['visitas', 'visitas_entregadas', 'codigo_complemento'],
                batch_size=500)

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
