from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context


class Command(BaseCommand):
    help = 'Diagnostico de por que rutear devuelve 0 rutas'

    def add_arguments(self, parser):
        parser.add_argument('schema', type=str)

    def handle(self, *args, **options):
        schema = options['schema']
        with schema_context(schema):
            from ruteo.models.visita import RutVisita
            from ruteo.models.vehiculo import RutVehiculo
            from ruteo.models.flota import RutFlota
            from ruteo.models.franja import RutFranja
            from general.models.configuracion import GenConfiguracion

            self.stdout.write(f'\n=== Diagnostico rutear para: {schema} ===\n')

            # 1. Configuracion
            config = GenConfiguracion.objects.filter(pk=1).values(
                'rut_rutear_franja', 'rut_direccion_origen', 'rut_latitud', 'rut_longitud', 'rut_hora_inicio'
            ).first()
            self.stdout.write(f'Configuracion: {config}\n')

            # 2. Visitas pendientes
            pendientes = RutVisita.objects.filter(
                estado_despacho=False, estado_decodificado=True
            ).values('id', 'numero', 'peso', 'tiempo', 'tiempo_servicio', 'tiempo_trayecto',
                     'franja_id', 'franja_codigo', 'cita_inicio', 'cita_fin', 'cita_tipo',
                     'latitud', 'longitud', 'estado_decodificado')
            self.stdout.write(f'\nVisitas pendientes ({pendientes.count()}):')
            for v in pendientes:
                self.stdout.write(f'  #{v["numero"]}: peso={v["peso"]} tiempo={v["tiempo"]} '
                                  f'franja_id={v["franja_id"]} franja_codigo={v["franja_codigo"]} '
                                  f'cita={v["cita_inicio"]}-{v["cita_fin"]} tipo={v["cita_tipo"]} '
                                  f'lat={v["latitud"]} lng={v["longitud"]}')

            # 3. Flota disponible
            flota = RutFlota.objects.filter(
                vehiculo__estado_asignado=False
            ).select_related('vehiculo').order_by('prioridad')
            self.stdout.write(f'\nFlota disponible ({flota.count()}):')
            for f in flota:
                v = f.vehiculo
                franjas = list(v.franjas.values_list('id', 'codigo'))
                self.stdout.write(f'  {v.placa}: capacidad={v.capacidad} tiempo={v.tiempo} '
                                  f'asignado={v.estado_asignado} franjas={franjas}')

            # 4. Vehiculos totales
            todos = RutVehiculo.objects.all().values('id', 'placa', 'capacidad', 'tiempo', 'estado_asignado')
            self.stdout.write(f'\nVehiculos totales ({todos.count()}):')
            for v in todos:
                self.stdout.write(f'  {v["placa"]}: capacidad={v["capacidad"]} tiempo={v["tiempo"]} asignado={v["estado_asignado"]}')

            # 5. Franjas
            franjas = RutFranja.objects.all().values('id', 'codigo', 'nombre')
            self.stdout.write(f'\nFranjas ({franjas.count()}):')
            for fr in franjas:
                self.stdout.write(f'  id={fr["id"]} codigo={fr["codigo"]} nombre={fr["nombre"]}')

            # 6. Verificar compatibilidad
            self.stdout.write(f'\n=== Verificacion de compatibilidad ===')
            rutear_franja = config.get('rut_rutear_franja', False) if config else False
            self.stdout.write(f'rutear_franja: {rutear_franja}')

            for f in flota:
                v = f.vehiculo
                franjas_vehiculo = set(v.franjas.values_list('id', flat=True))
                for vis in pendientes:
                    puede = True
                    razon = 'OK'
                    if vis['peso'] is None or vis['tiempo'] is None:
                        puede = False
                        razon = f'peso={vis["peso"]} o tiempo={vis["tiempo"]} es None'
                    elif v.capacidad is None or v.tiempo is None:
                        puede = False
                        razon = f'vehiculo capacidad={v.capacidad} o tiempo={v.tiempo} es None'
                    elif vis['peso'] > v.capacidad:
                        puede = False
                        razon = f'peso {vis["peso"]} > capacidad {v.capacidad}'
                    elif vis['tiempo'] > v.tiempo:
                        puede = False
                        razon = f'tiempo {vis["tiempo"]} > tiempo vehiculo {v.tiempo}'
                    elif rutear_franja and vis['franja_id'] and vis['franja_id'] not in franjas_vehiculo:
                        puede = False
                        razon = f'franja {vis["franja_id"]} no en vehiculo {franjas_vehiculo}'
                    self.stdout.write(f'  {v.placa} + #{vis["numero"]}: {"SI" if puede else "NO"} - {razon}')

            self.stdout.write(self.style.SUCCESS('\nDiagnostico completado'))
