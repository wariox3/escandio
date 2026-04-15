import logging
import math
from datetime import timedelta
from django.utils import timezone
from shapely.geometry import Point, Polygon
from general.models.configuracion import GenConfiguracion
from ruteo.models.alerta import RutAlerta
from ruteo.models.franja import RutFranja
from ruteo.models.ubicacion import RutUbicacion
from ruteo.models.visita import RutVisita

logger = logging.getLogger(__name__)


class AlertaServicio:

    @staticmethod
    def _distancia_metros(lat1, lng1, lat2, lng2):
        R = 6371000.0
        f1 = math.radians(float(lat1))
        f2 = math.radians(float(lat2))
        df = math.radians(float(lat2) - float(lat1))
        dl = math.radians(float(lng2) - float(lng1))
        a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @staticmethod
    def evaluar(ubicacion):
        if not ubicacion.despacho_id:
            return
        config = GenConfiguracion.objects.filter(pk=1).values(
            'rut_alerta_parada_activa',
            'rut_alerta_parada_minutos',
            'rut_alerta_parada_radio_metros',
            'rut_alerta_geocerca_activa',
        ).first()
        if not config:
            return
        try:
            if config.get('rut_alerta_parada_activa'):
                AlertaServicio._detectar_parada(ubicacion, config)
            if config.get('rut_alerta_geocerca_activa'):
                AlertaServicio._detectar_fuera_geocerca(ubicacion)
        except Exception as e:
            logger.error(f'Error evaluando alertas para ubicacion {ubicacion.id}: {e}')

    @staticmethod
    def _detectar_parada(ubicacion, config):
        minutos = config.get('rut_alerta_parada_minutos') or 15
        radio = config.get('rut_alerta_parada_radio_metros') or 80
        ventana = ubicacion.fecha - timedelta(minutes=minutos)

        previas = RutUbicacion.objects.filter(
            despacho_id=ubicacion.despacho_id,
            usuario_id=ubicacion.usuario_id,
            fecha__gte=ventana,
            fecha__lt=ubicacion.fecha,
        ).only('latitud', 'longitud', 'fecha').order_by('fecha')

        if not previas.exists():
            return

        primera = previas.first()
        duracion = (ubicacion.fecha - primera.fecha).total_seconds() / 60
        if duracion < minutos:
            return

        for u in previas:
            d = AlertaServicio._distancia_metros(ubicacion.latitud, ubicacion.longitud, u.latitud, u.longitud)
            if d > radio:
                return

        existe = RutAlerta.objects.filter(
            despacho_id=ubicacion.despacho_id,
            usuario_id=ubicacion.usuario_id,
            tipo='parada_prolongada',
            leida=False,
        ).exists()
        if existe:
            return

        RutAlerta.objects.create(
            tipo='parada_prolongada',
            despacho_id=ubicacion.despacho_id,
            usuario_id=ubicacion.usuario_id,
            latitud=ubicacion.latitud,
            longitud=ubicacion.longitud,
            duracion_minutos=int(duracion),
            mensaje=f'Vehiculo detenido por {int(duracion)} minutos',
        )

    @staticmethod
    def _detectar_fuera_geocerca(ubicacion):
        visita = RutVisita.objects.filter(
            despacho_id=ubicacion.despacho_id,
            estado_entregado=False,
            estado_devolucion=False,
            franja_id__isnull=False,
        ).order_by('orden').values('id', 'franja_id').first()
        if not visita:
            return

        franja = RutFranja.objects.filter(pk=visita['franja_id']).values('coordenadas').first()
        if not franja or not franja.get('coordenadas'):
            return

        try:
            poligono = Polygon([(c['lng'], c['lat']) for c in franja['coordenadas']])
        except Exception:
            return

        punto = Point(float(ubicacion.longitud), float(ubicacion.latitud))
        if poligono.contains(punto):
            return

        existe = RutAlerta.objects.filter(
            despacho_id=ubicacion.despacho_id,
            usuario_id=ubicacion.usuario_id,
            visita_id=visita['id'],
            tipo='fuera_geocerca',
            leida=False,
        ).exists()
        if existe:
            return

        RutAlerta.objects.create(
            tipo='fuera_geocerca',
            despacho_id=ubicacion.despacho_id,
            visita_id=visita['id'],
            usuario_id=ubicacion.usuario_id,
            latitud=ubicacion.latitud,
            longitud=ubicacion.longitud,
            mensaje='Vehiculo fuera de la geocerca asignada',
        )
