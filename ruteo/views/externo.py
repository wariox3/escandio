from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from general.permisos.api_key import TieneApiKey
from general.models.ciudad import GenCiudad
from general.models.estado import GenEstado
from general.models.archivo import GenArchivo
from ruteo.models.visita import RutVisita
from ruteo.models.novedad import RutNovedad
from ruteo.models.franja import RutFranja
from ruteo.serializers.visita import RutVisitaSerializador
from ruteo.servicios.visita import VisitaServicio
from contenedor.servicios.direccion import DireccionServicio
from utilidades.backblaze import Backblaze
from datetime import datetime
import base64
import logging

logger = logging.getLogger('django')


@api_view(['POST'])
@authentication_classes([])
@permission_classes([TieneApiKey])
def crear_guia(request):
    data = request.data

    campos_requeridos = ['numero', 'documento', 'destinatario', 'direccion', 'ciudad', 'departamento']
    faltantes = [c for c in campos_requeridos if not data.get(c)]
    if faltantes:
        return Response(
            {'mensaje': f'Campos requeridos faltantes: {", ".join(faltantes)}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Buscar ciudad por nombre + departamento
    departamento_nombre = str(data['departamento']).strip()
    ciudad_nombre = str(data['ciudad']).strip()

    estado = GenEstado.objects.filter(nombre__iexact=departamento_nombre).first()
    if not estado:
        return Response(
            {'mensaje': f'Departamento no encontrado: {departamento_nombre}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    ciudad = GenCiudad.objects.filter(nombre__iexact=ciudad_nombre, estado=estado).first()
    if not ciudad:
        return Response(
            {'mensaje': f'Ciudad no encontrada: {ciudad_nombre} en {departamento_nombre}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Limpiar y decodificar dirección
    direccion_limpia = VisitaServicio.limpiar_direccion(data['direccion'])
    franjas = RutFranja.objects.all()

    visita_data = {
        'numero': data['numero'],
        'documento': str(data['documento'])[:30],
        'destinatario': data['destinatario'],
        'destinatario_direccion': direccion_limpia,
        'destinatario_telefono': str(data.get('telefono', '') or '')[:50],
        'destinatario_correo': data.get('correo', ''),
        'unidades': data.get('unidades', 0),
        'peso': data.get('peso', 0),
        'volumen': data.get('volumen', 0),
        'tiempo_servicio': data.get('tiempo_servicio', 0),
        'ciudad_id': ciudad.id,
        'fecha': datetime.now(),
        'cita_inicio': data.get('cita_inicio'),
        'cita_fin': data.get('cita_fin'),
        'estado_decodificado': False,
        'estado_decodificado_alerta': False,
        'estado_franja': False,
        'franja': None,
        'latitud': None,
        'longitud': None,
        'resultados': None,
    }

    # Decodificar dirección (cache o Google Maps)
    if direccion_limpia:
        respuesta = DireccionServicio.decodificar(direccion_limpia)
        if respuesta['error'] == False:
            direccion = respuesta['datos']
            visita_data['estado_decodificado'] = True
            visita_data['latitud'] = direccion['latitud']
            visita_data['longitud'] = direccion['longitud']
            visita_data['destinatario_direccion_formato'] = direccion['direccion_formato']
            visita_data['resultados'] = direccion['resultados']
            if direccion['cantidad_resultados'] > 1:
                visita_data['estado_decodificado_alerta'] = True

    # Asignar franja si se decodificó
    if visita_data['estado_decodificado'] == True:
        respuesta = VisitaServicio.ubicar_punto(franjas, visita_data['latitud'], visita_data['longitud'])
        if respuesta['encontrado']:
            visita_data['franja'] = respuesta['franja']['id']
            visita_data['estado_franja'] = True

    serializer = RutVisitaSerializador(data=visita_data)
    if serializer.is_valid():
        visita = serializer.save(api_key=request.api_key)
        return Response({
            'mensaje': 'Guía creada exitosamente',
            'id': visita.id,
            'decodificada': visita.estado_decodificado or False,
        }, status=status.HTTP_201_CREATED)
    else:
        return Response(
            {'mensaje': 'Error en los datos', 'errores': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET'])
@authentication_classes([])
@permission_classes([TieneApiKey])
def consultar_estado(request):
    numero = request.query_params.get('numero')
    documento = request.query_params.get('documento')

    if not numero and not documento:
        return Response(
            {'mensaje': 'Debe enviar el parámetro numero o documento'},
            status=status.HTTP_400_BAD_REQUEST
        )

    visitas = RutVisita.objects.select_related('despacho').filter(api_key=request.api_key)
    if numero:
        visitas = visitas.filter(numero=numero)
    if documento:
        visitas = visitas.filter(documento=documento)

    visitas = visitas.order_by('-id')
    if not visitas.exists():
        return Response(
            {'mensaje': 'No se encontraron guías'},
            status=status.HTTP_404_NOT_FOUND
        )

    resultados = []
    backblaze = None

    for visita in visitas:
        # Determinar estado actual
        if visita.estado_entregado:
            estado_actual = 'ENTREGADO'
        elif visita.estado_novedad:
            estado_actual = 'NOVEDAD'
        elif visita.estado_despacho:
            estado_actual = 'DESPACHADO'
        else:
            estado_actual = 'PENDIENTE'

        guia = {
            'id': visita.id,
            'numero': visita.numero,
            'documento': visita.documento,
            'destinatario': visita.destinatario,
            'estado': estado_actual,
            'despacho': None,
            'novedades': [],
            'entrega': None,
        }

        # DESPACHO
        if visita.estado_despacho and visita.despacho:
            guia['despacho'] = {
                'fecha': visita.despacho.fecha_salida,
            }

        # NOVEDADES
        novedades = RutNovedad.objects.filter(visita=visita).select_related('novedad_tipo').order_by('-id')
        for novedad in novedades:
            novedad_data = {
                'tipo': novedad.novedad_tipo.nombre if novedad.novedad_tipo else None,
                'fecha': novedad.fecha,
                'descripcion': novedad.descripcion,
                'estado_solucion': novedad.estado_solucion,
                'solucion': novedad.solucion,
                'foto': None,
            }
            # Primera foto de la novedad
            archivo = GenArchivo.objects.filter(
                modelo='RutNovedad', codigo=novedad.id, archivo_tipo_id=2
            ).first()
            if archivo:
                try:
                    if backblaze is None:
                        backblaze = Backblaze()
                    contenido = backblaze.descargar_bytes(archivo.almacenamiento_id)
                    if contenido:
                        novedad_data['foto'] = base64.b64encode(contenido).decode('utf-8')
                except Exception as e:
                    logger.error(f'Error descargando foto novedad {novedad.id}: {e}')

            guia['novedades'].append(novedad_data)

        # ENTREGA
        if visita.estado_entregado:
            entrega_data = {
                'fecha': visita.fecha_entrega,
                'datos': visita.datos_entrega or {},
                'fotos': [],
                'firma': None,
            }

            # Fotos de entrega (hasta 5)
            archivos_fotos = GenArchivo.objects.filter(
                modelo='RutVisita', codigo=visita.id, archivo_tipo_id=2
            ).order_by('id')[:5]
            for archivo in archivos_fotos:
                try:
                    if backblaze is None:
                        backblaze = Backblaze()
                    contenido = backblaze.descargar_bytes(archivo.almacenamiento_id)
                    if contenido:
                        entrega_data['fotos'].append(base64.b64encode(contenido).decode('utf-8'))
                except Exception as e:
                    logger.error(f'Error descargando foto entrega visita {visita.id}: {e}')

            # Firma
            archivo_firma = GenArchivo.objects.filter(
                modelo='RutVisita', codigo=visita.id, archivo_tipo_id=3
            ).first()
            if archivo_firma:
                try:
                    if backblaze is None:
                        backblaze = Backblaze()
                    contenido = backblaze.descargar_bytes(archivo_firma.almacenamiento_id)
                    if contenido:
                        entrega_data['firma'] = base64.b64encode(contenido).decode('utf-8')
                except Exception as e:
                    logger.error(f'Error descargando firma visita {visita.id}: {e}')

            guia['entrega'] = entrega_data

        resultados.append(guia)

    return Response(resultados, status=status.HTTP_200_OK)
