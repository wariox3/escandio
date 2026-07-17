"""Registro de novedades v2.

Reimplementa ruteo.views.novedad.RutNovedadViewSet.nuevo_action sin tocar la
view legacy congelada.
"""
import base64
import logging

from django.db import transaction

from general.models.archivo import GenArchivo
from general.models.configuracion import GenConfiguracion
from movil.services.errores import EvidenciaNoGuardada
from ruteo.models.novedad import RutNovedad
from ruteo.models.novedad_tipo import RutNovedadTipo
from ruteo.servicios.notificacion import NotificacionServicio
from utilidades.backblaze import Backblaze
from utilidades.holmio import Holmio
from utilidades.imagen import Imagen

logger = logging.getLogger(__name__)


def _a_base64(imagenes):
    resultado = []
    for imagen in (imagenes or []):
        imagen.seek(0)
        resultado.append({'base64': base64.b64encode(imagen.read()).decode('utf-8')})
    return resultado


def _guardar_imagenes(novedad_id, imagenes, schema_name):
    # Igual que en entrega: un fallo transitorio de Backblaze no debe volverse
    # 500 opaco ("servidor fuera de linea" + bucle). Se convierte en
    # EvidenciaNoGuardada -> revierte la novedad -> la vista responde limpio para
    # reintentar. Se loguea (exc_info) para verlo en Sentry.
    try:
        backblaze = Backblaze()
        for idx, imagen in enumerate(imagenes):
            contenido = Imagen.comprimir_imagen_jpg(imagen, calidad=20, max_width=1920)
            nombre = f'{novedad_id}_{idx}.jpg'
            id_alm, tamano, tipo, uuid, url = backblaze.subir_data(contenido, schema_name, nombre)
            GenArchivo.objects.create(
                archivo_tipo_id=2,
                almacenamiento_id=id_alm,
                nombre=nombre,
                tipo=tipo,
                tamano=tamano,
                uuid=uuid,
                codigo=novedad_id,
                modelo='RutNovedad',
                url=url,
            )
    except Exception as e:
        logger.exception(
            'novedad v2: fallo al guardar imagenes (novedad=%s)', novedad_id,
        )
        raise EvidenciaNoGuardada() from e


def _sincronizar_complemento(novedad, imagenes_b64):
    """Sincroniza la novedad con el sistema externo Holmio."""
    parametros = {
        'codigoGuia': novedad.visita.numero,
        'codigoNovedadTipo': novedad.novedad_tipo_id,
        'descripcion': novedad.descripcion,
        'usuario': 'ruteo',
    }
    if imagenes_b64:
        parametros['imagenes'] = imagenes_b64
    respuesta = Holmio().novedad(parametros)
    if respuesta.get('error') is False:
        novedad.nuevo_complemento = True
        novedad.save(update_fields=['nuevo_complemento'])


def _notificar(novedad, descripcion, novedad_tipo_id, tenant):
    """Notifica la novedad al cliente. Falla silenciosa."""
    try:
        motivo = (descripcion or '').strip()
        if not motivo:
            nombre = RutNovedadTipo.objects.filter(
                pk=novedad_tipo_id,
            ).values_list('nombre', flat=True).first()
            motivo = nombre or 'incidencia en la entrega'
        NotificacionServicio.notificar_visita_novedad(
            visita_id=novedad.visita_id,
            motivo=motivo,
            schema_name=tenant.schema_name,
            nombre_empresa=tenant.nombre,
            contenedor_id=tenant.id,
        )
    except Exception:  # noqa: BLE001
        pass


def registrar_novedad(visita, novedad_tipo_id, fecha, descripcion, movil_token, imagenes, tenant):
    """Crea la novedad (idempotente por movil_token) y devuelve la novedad.

    `fecha` ya es un datetime aware. `visita` ya fue validada.
    """
    existente = RutNovedad.objects.filter(movil_token=movil_token).first()
    if existente:
        return existente

    with transaction.atomic():
        novedad = RutNovedad.objects.create(
            fecha=fecha,
            visita=visita,
            novedad_tipo_id=novedad_tipo_id,
            descripcion=descripcion,
            movil_token=movil_token,
        )
        visita.estado_novedad = True
        visita.save(update_fields=['estado_novedad'])
        if visita.despacho:
            despacho = visita.despacho
            despacho.visitas_novedad = (despacho.visitas_novedad or 0) + 1
            despacho.save(update_fields=['visitas_novedad'])

        if imagenes:
            _guardar_imagenes(novedad.id, imagenes, tenant.schema_name)

        configuracion = GenConfiguracion.objects.filter(pk=1).values(
            'rut_sincronizar_complemento',
        ).first()
        if configuracion and configuracion['rut_sincronizar_complemento']:
            _sincronizar_complemento(novedad, _a_base64(imagenes))

    _notificar(novedad, descripcion, novedad_tipo_id, tenant)
    return novedad
