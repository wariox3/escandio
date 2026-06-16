import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
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
        self._logger = self._configurar_logger()
        contenedores = Contenedor.objects.exclude(schema_name='public')
        if options.get('schema'):
            contenedores = contenedores.filter(schema_name=options['schema'])

        hacer_entregas = not options['solo_novedades']
        hacer_novedades = not options['solo_entregas']

        self._log(f'inicio ({timezone.now():%Y-%m-%d %H:%M:%S})')
        contenedores_activos = 0
        totales = {'procesadas': 0, 'fallidas': 0, 'descartadas': 0}
        for contenedor in contenedores.order_by('schema_name'):
            try:
                with schema_context(contenedor.schema_name):
                    configuracion = GenConfiguracion.objects.filter(pk=1).values('rut_sincronizar_complemento').first()
                    if not (configuracion and configuracion['rut_sincronizar_complemento']):
                        continue
                    contenedores_activos += 1
                    if hacer_entregas:
                        self._procesar(contenedor.schema_name, 'entregas', ComplementoServicio.sincronizar_entregas, totales)
                    if hacer_novedades:
                        self._procesar(contenedor.schema_name, 'novedades', ComplementoServicio.sincronizar_novedades, totales)
            except Exception as e:
                self._log(f'{contenedor.schema_name}: ERROR - {e}', error=True)

        self._log(
            f"fin: {contenedores_activos} contenedores activos, "
            f"{totales['procesadas']} sincronizadas, {totales['fallidas']} con error, "
            f"{totales['descartadas']} descartadas"
        )

    def _procesar(self, schema, tipo, sincronizar, totales):
        resultado = self._drenar(sincronizar)
        totales['procesadas'] += resultado['procesadas']
        totales['fallidas'] += resultado['fallidas']
        totales['descartadas'] += resultado['descartadas']
        if resultado['procesadas'] or resultado['fallidas'] or resultado['descartadas']:
            self._log(
                f"{schema} [{tipo}]: {resultado['procesadas']} sincronizadas, "
                f"{resultado['fallidas']} con error, {resultado['descartadas']} descartadas"
            )

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

    def _log(self, mensaje, error=False):
        if error:
            self._logger.error(mensaje)
            self.stderr.write(self.style.ERROR(mensaje))
        else:
            self._logger.info(mensaje)
            self.stdout.write(mensaje)

    @staticmethod
    def _configurar_logger():
        logger = logging.getLogger('complemento.sincronizar')
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            logs_dir = Path(settings.BASE_DIR) / 'logs'
            logs_dir.mkdir(exist_ok=True)
            handler = logging.FileHandler(logs_dir / 'sincronizar_complemento.log')
            handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
            logger.addHandler(handler)
        return logger
