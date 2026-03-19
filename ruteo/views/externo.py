from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from general.permisos.api_key import TieneApiKey
from general.models.ciudad import GenCiudad
from general.models.estado import GenEstado
from ruteo.models.visita import RutVisita
from ruteo.models.franja import RutFranja
from ruteo.serializers.visita import RutVisitaSerializador
from ruteo.servicios.visita import VisitaServicio
from contenedor.servicios.direccion import DireccionServicio
from datetime import datetime
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
        visita = serializer.save()
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
