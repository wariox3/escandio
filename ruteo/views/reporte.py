from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from ruteo.models.despacho import RutDespacho
from contenedor.models import User
from contenedor.permisos import PermisoModuloVer


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

        conductor_ids = {r['conductor_id'] for r in registros if r['conductor_id']}
        nombres = {}
        if conductor_ids:
            for usuario in User.objects.filter(pk__in=conductor_ids).only('id', 'nombre', 'apellido'):
                nombre = f'{usuario.nombre or ""} {usuario.apellido or ""}'.strip()
                nombres[usuario.id] = nombre or None

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
