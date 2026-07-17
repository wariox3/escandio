"""Registro de entregas v2.

Reimplementa el cuerpo de ruteo.views.visita.RutVisitaViewSet.entrega_action
sin tocar la view legacy congelada.
"""
import base64
import logging

from django.db import transaction
from django.db.models import F

from general.models.archivo import GenArchivo
from general.models.configuracion import GenConfiguracion
from movil.services.errores import EvidenciaNoGuardada
from ruteo.models.despacho import RutDespacho
from ruteo.servicios.notificacion import NotificacionServicio
from ruteo.servicios.visita import VisitaServicio
from utilidades.backblaze import Backblaze
from utilidades.imagen import Imagen
from utilidades.utilidades import UtilidadGeneral

logger = logging.getLogger(__name__)


def _revincular_despacho(visita):
    """Re-vincula la visita a su despacho anterior si quedo detachada.

    Una visita puede perder el despacho si la web lo libero/anulo mientras la
    app la tenia cacheada offline. Si hay rastro, la reconectamos.
    """
    if visita.despacho_id is None and visita.despacho_anterior_id is not None:
        visita.despacho_id = visita.despacho_anterior_id
        visita.estado_despacho = True
        visita.despacho_anterior = None
        visita.save()


def _a_base64(archivos):
    resultado = []
    for archivo in (archivos or []):
        archivo.seek(0)
        resultado.append({'base64': base64.b64encode(archivo.read()).decode('utf-8')})
    return resultado


def _guardar_archivos(visita_id, archivos, schema_name, archivo_tipo_id, extension, comprimir):
    # Backblaze (auth + upload) hace red -> B2Error/timeout ante un fallo
    # transitorio. Sin este try, la excepcion subia sin atrapar -> 500 opaco ->
    # la app mostraba "servidor fuera de linea" y reintentaba en bucle. Ahora la
    # convertimos en EvidenciaNoGuardada: la transaccion de la entrega revierte
    # (no se da por entregada sin evidencia) y la vista responde un error LIMPIO
    # para que el conductor reintente. Se loguea (exc_info) para verlo en Sentry.
    try:
        backblaze = Backblaze()
        for idx, subido in enumerate(archivos):
            if comprimir:
                contenido = Imagen.comprimir_imagen_jpg(subido, calidad=20, max_width=1920)
            else:
                # Las firmas no se comprimen: el JPG dana el PNG.
                contenido = subido.read()
            nombre = f'{visita_id}_{idx}.{extension}'
            id_alm, tamano, tipo, uuid, url = backblaze.subir_data(contenido, schema_name, nombre)
            GenArchivo.objects.create(
                archivo_tipo_id=archivo_tipo_id,
                almacenamiento_id=id_alm,
                nombre=nombre,
                tipo=tipo,
                tamano=tamano,
                uuid=uuid,
                codigo=visita_id,
                modelo='RutVisita',
                url=url,
            )
    except Exception as e:
        logger.exception(
            'entrega v2: fallo al guardar evidencias (visita=%s, tipo_archivo=%s)',
            visita_id, archivo_tipo_id,
        )
        raise EvidenciaNoGuardada() from e


def registrar_entrega(visita, fecha_entrega, imagenes, firmas, datos_adicionales, tenant):
    """Marca la visita como entregada, sube evidencias y notifica al cliente.

    `visita` ya fue validada y NO esta entregada. `tenant` es request.tenant.
    """
    _revincular_despacho(visita)
    with transaction.atomic():
        datos_entrega = UtilidadGeneral.json_texto(datos_adicionales)
        visita.estado_entregado = True
        visita.fecha_entrega = fecha_entrega
        visita.datos_entrega = datos_entrega
        visita.save()
        RutDespacho.objects.filter(pk=visita.despacho_id).update(
            visitas_entregadas=F('visitas_entregadas') + 1,
        )
        if imagenes:
            _guardar_archivos(visita.id, imagenes, tenant.schema_name, 2, 'jpg', comprimir=True)
        if firmas:
            _guardar_archivos(visita.id, firmas, tenant.schema_name, 3, 'png', comprimir=False)

        configuracion = GenConfiguracion.objects.filter(pk=1).values(
            'rut_sincronizar_complemento',
        ).first()
        if configuracion and configuracion['rut_sincronizar_complemento']:
            VisitaServicio.entrega_complemento(
                visita, _a_base64(imagenes), _a_base64(firmas), datos_entrega,
            )

    # Tras commit: notificar al cliente. Falla silenciosa — la entrega ya quedo
    # registrada y no debe revertirse porque WhatsApp este caido.
    try:
        NotificacionServicio.notificar_visita_entregada(
            visita_id=visita.id,
            schema_name=tenant.schema_name,
            nombre_empresa=tenant.nombre,
            contenedor_id=tenant.id,
        )
    except Exception:  # noqa: BLE001
        pass
