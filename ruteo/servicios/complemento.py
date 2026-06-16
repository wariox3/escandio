import base64

from general.models.archivo import GenArchivo
from ruteo.models.novedad import RutNovedad
from ruteo.models.visita import RutVisita
from ruteo.servicios.visita import VisitaServicio
from utilidades.backblaze import Backblaze
from utilidades.holmio import Holmio


class ComplementoServicio:
    LIMITE_LOTE = 50
    LIMITE_INTENTOS = 5

    @staticmethod
    def _archivos_b64(backblaze, modelo, codigo, archivo_tipo_id, comprimido):
        resultado = []
        archivos = GenArchivo.objects.filter(modelo=modelo, codigo=codigo, archivo_tipo_id=archivo_tipo_id)
        for archivo in archivos:
            contenido = backblaze.descargar_bytes(archivo.almacenamiento_id)
            if contenido is not None:
                item = {'base64': base64.b64encode(contenido).decode('utf-8')}
                if comprimido:
                    item['comprimido'] = True
                resultado.append(item)
        return resultado

    @classmethod
    def sincronizar_entregas(cls, limite_lote=None, limite_intentos=None, reiniciar_descartadas=False):
        limite_lote = limite_lote or cls.LIMITE_LOTE
        limite_intentos = limite_intentos or cls.LIMITE_INTENTOS
        backblaze = Backblaze()
        pendientes = RutVisita.objects.filter(estado_entregado=True, estado_entregado_complemento=False)
        if reiniciar_descartadas:
            pendientes.filter(entrega_complemento_intentos__gte=limite_intentos).update(entrega_complemento_intentos=0)
        visitas = pendientes.filter(entrega_complemento_intentos__lt=limite_intentos)
        total_pendientes = visitas.count()
        procesadas = 0
        fallidas = []
        for visita in visitas.order_by('entrega_complemento_intentos', 'id')[:limite_lote]:
            try:
                imagenes_b64 = cls._archivos_b64(backblaze, 'RutVisita', visita.id, 2, comprimido=True)
                firmas_b64 = cls._archivos_b64(backblaze, 'RutVisita', visita.id, 3, comprimido=False)
                respuesta = VisitaServicio.entrega_complemento(visita, imagenes_b64, firmas_b64, visita.datos_entrega)
                if respuesta['error']:
                    fallidas.append({'id': visita.id, 'numero': visita.numero, 'mensaje': respuesta['mensaje']})
                else:
                    procesadas += 1
            except Exception as e:
                fallidas.append({'id': visita.id, 'numero': visita.numero, 'mensaje': str(e)})
            if procesadas == 0 and len(fallidas) >= 5:
                break
        descartadas = pendientes.filter(entrega_complemento_intentos__gte=limite_intentos).count()
        return cls._resultado('Entrega complemento', total_pendientes, procesadas, fallidas, descartadas, limite_intentos)

    @classmethod
    def sincronizar_novedades(cls, limite_lote=None, limite_intentos=None, reiniciar_descartadas=False):
        limite_lote = limite_lote or cls.LIMITE_LOTE
        limite_intentos = limite_intentos or cls.LIMITE_INTENTOS
        backblaze = Backblaze()
        pendientes = RutNovedad.objects.filter(nuevo_complemento=False)
        if reiniciar_descartadas:
            pendientes.filter(nuevo_complemento_intentos__gte=limite_intentos).update(nuevo_complemento_intentos=0)
        novedades = pendientes.filter(nuevo_complemento_intentos__lt=limite_intentos)
        total_pendientes = novedades.count()
        procesadas = 0
        fallidas = []
        for novedad in novedades.select_related('visita').order_by('nuevo_complemento_intentos', 'id')[:limite_lote]:
            try:
                imagenes_b64 = cls._archivos_b64(backblaze, 'RutNovedad', novedad.id, 2, comprimido=True)
                respuesta = cls.enviar_novedad(novedad, imagenes_b64)
                if respuesta['error']:
                    fallidas.append({'id': novedad.id, 'numero': novedad.visita.numero, 'mensaje': respuesta['mensaje']})
                else:
                    procesadas += 1
            except Exception as e:
                fallidas.append({'id': novedad.id, 'numero': novedad.visita.numero, 'mensaje': str(e)})
            if procesadas == 0 and len(fallidas) >= 5:
                break
        descartadas = pendientes.filter(nuevo_complemento_intentos__gte=limite_intentos).count()
        return cls._resultado('Novedad complemento', total_pendientes, procesadas, fallidas, descartadas, limite_intentos)

    @staticmethod
    def enviar_novedad(novedad: RutNovedad, imagenes_b64):
        holmio = Holmio()
        parametros = {
            'codigoGuia': novedad.visita.numero,
            'codigoNovedadTipo': novedad.novedad_tipo_id,
            'descripcion': novedad.descripcion,
            'usuario': 'ruteo'
        }
        if imagenes_b64:
            parametros['imagenes'] = imagenes_b64
        respuesta = holmio.novedad(parametros)
        if respuesta['error'] == False:
            novedad.nuevo_complemento = True
            novedad.save(update_fields=['nuevo_complemento'])
            return {'error': False}
        if respuesta.get('rechazo'):
            novedad.nuevo_complemento_intentos += 1
            novedad.save(update_fields=['nuevo_complemento_intentos'])
        return respuesta

    @staticmethod
    def _resultado(prefijo, total_pendientes, procesadas, fallidas, descartadas, limite_intentos):
        sin_procesar = total_pendientes - procesadas - len(fallidas)
        mensaje = f'{prefijo}: {procesadas} sincronizadas, {len(fallidas)} con error, {sin_procesar} sin procesar'
        if descartadas:
            mensaje += f', {descartadas} descartadas tras {limite_intentos} intentos'
        return {
            'mensaje': mensaje,
            'procesadas': procesadas,
            'fallidas': fallidas,
            'sin_procesar': sin_procesar,
            'descartadas': descartadas,
        }
