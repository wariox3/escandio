from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from contenedor.models import Contenedor
from general.models.configuracion import GenConfiguracion
from ruteo.servicios.complemento import ComplementoServicio

MAX_LOTES_POR_TENANT = 100


class Command(BaseCommand):
    help = 'Sincroniza con Complemento las entregas y novedades pendientes de todos los contenedores.'

    def add_arguments(self, parser):
        parser.add_argument('--schema', help='Procesa solo el contenedor indicado (schema_name).')
        parser.add_argument('--solo-entregas', action='store_true', help='Sincroniza solo entregas.')
        parser.add_argument('--solo-novedades', action='store_true', help='Sincroniza solo novedades.')

    def handle(self, *args, **options):
        contenedores = Contenedor.objects.exclude(schema_name='public')
        if options.get('schema'):
            contenedores = contenedores.filter(schema_name=options['schema'])

        hacer_entregas = not options['solo_novedades']
        hacer_novedades = not options['solo_entregas']

        for contenedor in contenedores.order_by('schema_name'):
            try:
                with schema_context(contenedor.schema_name):
                    configuracion = GenConfiguracion.objects.filter(pk=1).values('rut_sincronizar_complemento').first()
                    if not (configuracion and configuracion['rut_sincronizar_complemento']):
                        continue

                    if hacer_entregas:
                        entregas = self._drenar(ComplementoServicio.sincronizar_entregas)
                        self._reportar(contenedor.schema_name, 'entregas', entregas)
                    if hacer_novedades:
                        novedades = self._drenar(ComplementoServicio.sincronizar_novedades)
                        self._reportar(contenedor.schema_name, 'novedades', novedades)
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'{contenedor.schema_name}: ERROR - {e}'))

    @staticmethod
    def _drenar(sincronizar):
        procesadas = 0
        fallidas = 0
        descartadas = 0
        for _ in range(MAX_LOTES_POR_TENANT):
            resultado = sincronizar()
            procesadas += resultado['procesadas']
            fallidas = len(resultado['fallidas'])
            descartadas = resultado['descartadas']
            if resultado['procesadas'] == 0 or resultado['sin_procesar'] == 0:
                break
        return {'procesadas': procesadas, 'fallidas': fallidas, 'descartadas': descartadas}

    def _reportar(self, schema, tipo, resultado):
        if resultado['procesadas'] or resultado['fallidas'] or resultado['descartadas']:
            self.stdout.write(
                f"{schema} [{tipo}]: {resultado['procesadas']} sincronizadas, "
                f"{resultado['fallidas']} con error, {resultado['descartadas']} descartadas"
            )
