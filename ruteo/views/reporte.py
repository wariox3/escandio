from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q
from ruteo.models.despacho import RutDespacho
from ruteo.models.visita import RutVisita
from ruteo.models.franja import RutFranja
from contenedor.models import User
from contenedor.permisos import PermisoModuloVer


def _nombres_conductor(conductor_ids):
    """Mapa {id: 'Nombre Apellido'} para los conductores dados."""
    nombres = {}
    if conductor_ids:
        for usuario in User.objects.filter(pk__in=conductor_ids).only('id', 'nombre', 'apellido'):
            nombre = f'{usuario.nombre or ""} {usuario.apellido or ""}'.strip()
            nombres[usuario.id] = nombre or None
    return nombres


class ReporteMensajeroView(APIView):
    permission_classes = [IsAuthenticated, PermisoModuloVer('reporte')]

    def get(self, request):
        fecha_desde = request.query_params.get('fecha_desde') or request.query_params.get('fecha__gte')
        fecha_hasta = request.query_params.get('fecha_hasta') or request.query_params.get('fecha__lte')

        despachos = RutDespacho.objects.filter(estado_anulado=False)
        if fecha_desde:
            despachos = despachos.filter(fecha__date__gte=fecha_desde)
        if fecha_hasta:
            despachos = despachos.filter(fecha__date__lte=fecha_hasta)

        registros = list(
            despachos.values(
                'id',
                'fecha',
                'conductor_id',
                'visitas',
                'visitas_entregadas',
                'visitas_novedad',
                'vehiculo__placa',
            ).order_by('-fecha')
        )

        nombres = _nombres_conductor({r['conductor_id'] for r in registros if r['conductor_id']})

        resultados = [
            {
                'id': r['id'],
                'fecha': r['fecha'],
                'conductor_id': r['conductor_id'],
                'conductor_nombre': nombres.get(r['conductor_id']),
                'vehiculo__placa': r['vehiculo__placa'],
                'visitas': r['visitas'],
                'visitas_entregadas': r['visitas_entregadas'],
                'visitas_novedad': r['visitas_novedad'],
            }
            for r in registros
        ]

        return Response({'count': len(resultados), 'results': resultados}, status=status.HTTP_200_OK)


class ReporteMensajeroEntregasView(APIView):
    """Relacion guia por guia con la zona (franja) donde cae la entrega.

    La zona es factor de pago del mensajero. Se entrega:
      - 'resumen': conteo por (mensajero x zona) -> alimenta el pago. Se agrega
        en la BD y NUNCA se trunca, asi los totales de pago siempre son completos.
      - 'relacion': el detalle guia por guia (para verificar), acotado a
        LIMITE_RELACION con bandera 'truncado' porque un mes puede traer decenas
        de miles de guias.

    La zona vive denormalizada en la visita (franja_id / franja_codigo); el
    nombre se resuelve contra RutFranja. Una guia sin franja (direccion fuera de
    todo poligono, o franja no dibujada) sale con zona en null -> el front la
    muestra como "Sin zona" para que se vea y se corrija, no se descarta.
    """

    permission_classes = [IsAuthenticated, PermisoModuloVer('reporte')]
    # El detalle se acota; el resumen de pago se agrega aparte y va completo.
    LIMITE_RELACION = 20000

    def get(self, request):
        fecha_desde = request.query_params.get('fecha_desde') or request.query_params.get('fecha__gte')
        fecha_hasta = request.query_params.get('fecha_hasta') or request.query_params.get('fecha__lte')

        # Asignadas = guias vinculadas a un despacho no anulado.
        visitas = RutVisita.objects.filter(despacho__isnull=False, despacho__estado_anulado=False)
        if fecha_desde:
            visitas = visitas.filter(despacho__fecha__date__gte=fecha_desde)
        if fecha_hasta:
            visitas = visitas.filter(despacho__fecha__date__lte=fecha_hasta)

        # Resumen por (mensajero x zona) -> pago. Agregado en BD, completo.
        resumen_bruto = list(
            visitas.values('despacho__conductor_id', 'franja_id', 'franja_codigo').annotate(
                asignadas=Count('id'),
                entregadas=Count('id', filter=Q(estado_entregado=True)),
                novedades=Count('id', filter=Q(estado_novedad=True)),
            )
        )

        # Relacion detalle, acotada. Se pide un registro de mas para saber si hay
        # mas alla del limite (truncado) sin un count() aparte.
        registros = list(
            visitas.values(
                'id', 'numero', 'documento', 'destinatario', 'destinatario_direccion',
                'despacho_id', 'despacho__fecha', 'despacho__conductor_id', 'despacho__vehiculo__placa',
                'franja_id', 'franja_codigo', 'estado_entregado', 'estado_novedad', 'fecha_entrega',
            ).order_by('-despacho__fecha', 'despacho_id', 'orden')[:self.LIMITE_RELACION + 1]
        )
        truncado = len(registros) > self.LIMITE_RELACION
        registros = registros[:self.LIMITE_RELACION]

        nombres = _nombres_conductor(
            {r['despacho__conductor_id'] for r in registros if r['despacho__conductor_id']}
            | {r['despacho__conductor_id'] for r in resumen_bruto if r['despacho__conductor_id']}
        )

        franja_ids = (
            {r['franja_id'] for r in registros if r['franja_id']}
            | {r['franja_id'] for r in resumen_bruto if r['franja_id']}
        )
        zonas = {}
        if franja_ids:
            for franja in RutFranja.objects.filter(pk__in=franja_ids).only('id', 'nombre', 'codigo'):
                zonas[franja.id] = {'nombre': franja.nombre, 'codigo': franja.codigo}

        def _estado(entregado, novedad):
            if entregado:
                return 'entregada'
            if novedad:
                return 'novedad'
            return 'pendiente'

        relacion = [
            {
                'id': r['id'],
                'fecha': r['despacho__fecha'],
                'fecha_entrega': r['fecha_entrega'],
                'despacho_id': r['despacho_id'],
                'conductor_id': r['despacho__conductor_id'],
                'conductor_nombre': nombres.get(r['despacho__conductor_id']),
                'placa': r['despacho__vehiculo__placa'],
                'numero': r['numero'],
                'documento': r['documento'],
                'destinatario': r['destinatario'],
                'destinatario_direccion': r['destinatario_direccion'],
                'zona_id': r['franja_id'],
                'zona_codigo': r['franja_codigo'],
                'zona_nombre': zonas.get(r['franja_id'], {}).get('nombre'),
                'estado': _estado(r['estado_entregado'], r['estado_novedad']),
            }
            for r in registros
        ]

        resumen = [
            {
                'conductor_id': r['despacho__conductor_id'],
                'conductor_nombre': nombres.get(r['despacho__conductor_id']),
                'zona_id': r['franja_id'],
                'zona_codigo': r['franja_codigo'],
                'zona_nombre': zonas.get(r['franja_id'], {}).get('nombre'),
                'asignadas': r['asignadas'],
                'entregadas': r['entregadas'],
                'novedades': r['novedades'],
            }
            for r in resumen_bruto
        ]

        return Response(
            {
                'relacion': relacion,
                'relacion_count': len(relacion),
                'truncado': truncado,
                'resumen': resumen,
            },
            status=status.HTTP_200_OK,
        )
