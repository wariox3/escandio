from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context
from contenedor.models import Contenedor
from ruteo.models.despacho import RutDespacho
from ruteo.models.visita import RutVisita
from ruteo.models.notificacion import RutNotificacion
from django.db.models import Sum, Count


class Command(BaseCommand):
    help = 'Diagnostico del endpoint admin-entregas'

    def handle(self, *args, **options):
        contenedores = Contenedor.objects.exclude(schema_name='public').values(
            'id', 'schema_name', 'nombre', 'fecha_ultima_conexion'
        ).order_by('nombre')

        self.stdout.write(f'\nTotal contenedores: {len(contenedores)}\n')
        self.stdout.write('-' * 80)

        for c in contenedores:
            try:
                with schema_context(c['schema_name']):
                    despachos = RutDespacho.objects.filter(
                        estado_aprobado=True,
                        estado_anulado=False,
                    ).aggregate(
                        total=Count('id'),
                        visitas=Sum('visitas'),
                        entregadas=Sum('visitas_entregadas'),
                    )
                    decodificadas = RutVisita.objects.filter(estado_decodificado=True).count()
                    try:
                        whatsapp = RutNotificacion.objects.filter(estado_enviado=True).count()
                    except Exception:
                        whatsapp = 'tabla no existe'

                self.stdout.write(
                    f"\n{c['nombre']} ({c['schema_name']}):"
                    f"\n  Despachos: {despachos['total']}"
                    f"\n  Visitas: {despachos['visitas']}"
                    f"\n  Entregadas: {despachos['entregadas']}"
                    f"\n  Decodificadas: {decodificadas}"
                    f"\n  WhatsApp: {whatsapp}"
                    f"\n  Ultima conexion: {c['fecha_ultima_conexion']}"
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"\n{c['schema_name']}: ERROR - {e}"))

        self.stdout.write('\n' + '-' * 80)
        self.stdout.write(self.style.SUCCESS('\nDiagnostico completado'))
