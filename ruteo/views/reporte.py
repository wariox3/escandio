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
from utilidades.excel_plantilla import ExcelPlantilla


def _nombres_conductor(conductor_ids):
    """Mapa {id: 'Nombre Apellido'} para los conductores dados."""
    nombres = {}
    if conductor_ids:
        for usuario in User.objects.filter(pk__in=conductor_ids).only('id', 'nombre', 'apellido'):
            nombre = f'{usuario.nombre or ""} {usuario.apellido or ""}'.strip()
            nombres[usuario.id] = nombre or None
    return nombres


def _rango_texto(fecha_desde, fecha_hasta):
    if fecha_desde and fecha_hasta:
        return f'Del {fecha_desde} al {fecha_hasta}'
    if fecha_desde:
        return f'Desde {fecha_desde}'
    if fecha_hasta:
        return f'Hasta {fecha_hasta}'
    return 'Todas las fechas'


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

        # Se cuentan las visitas REALES, no los contadores denormalizados del
        # despacho (visitas / visitas_entregadas / visitas_novedad): esos se
        # desincronizan (llegaban a dar asignadas < entregadas y no cuadraban con
        # el informe de zonas). Contando aca ambos informes salen de la misma
        # fuente y las asignadas nunca son menores que las entregadas (subconjunto).
        despachos = despachos.annotate(
            _asignadas=Count('visitas_despacho_rel'),
            _entregadas=Count('visitas_despacho_rel', filter=Q(visitas_despacho_rel__estado_entregado=True)),
            _novedades=Count('visitas_despacho_rel', filter=Q(visitas_despacho_rel__estado_novedad=True)),
        )

        registros = list(
            despachos.values(
                'id',
                'fecha',
                'conductor_id',
                '_asignadas',
                '_entregadas',
                '_novedades',
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
                'visitas': r['_asignadas'],
                'visitas_entregadas': r['_entregadas'],
                'visitas_novedad': r['_novedades'],
            }
            for r in registros
        ]

        if request.query_params.get('excel'):
            return self._exportar_excel(resultados, fecha_desde, fecha_hasta)

        return Response({'count': len(resultados), 'results': resultados}, status=status.HTTP_200_OK)

    def _exportar_excel(self, resultados, fecha_desde, fecha_hasta):
        # La agregacion (por mensajero/placa/dia + totales) tambien la hace el
        # front para mostrarla en pantalla; aca se replica para el Excel. Ambos
        # parten de las mismas filas por despacho, asi que dan el mismo numero.
        # Consolidar en una sola fuente queda como mejora futura.
        def dia(f):
            return f.date().isoformat() if f else ''

        def cumplimiento(entregadas, asignadas):
            # Igual que el front: 1 decimal, medio hacia arriba.
            return int(entregadas / asignadas * 1000 + 0.5) / 10 if asignadas else 0

        detalle = {}
        for r in resultados:
            clave = (r['conductor_id'], r['vehiculo__placa'], dia(r['fecha']))
            fila = detalle.get(clave)
            if fila is None:
                fila = {
                    'mensajero': r['conductor_nombre'] or 'Sin asignar',
                    'placa': r['vehiculo__placa'] or 'Sin placa',
                    'fecha': dia(r['fecha']),
                    'despachos': 0, 'asignadas': 0, 'entregadas': 0, 'novedades': 0,
                }
                detalle[clave] = fila
            fila['despachos'] += 1
            fila['asignadas'] += r['visitas'] or 0
            fila['entregadas'] += r['visitas_entregadas'] or 0
            fila['novedades'] += r['visitas_novedad'] or 0

        filas = sorted(detalle.values(), key=lambda f: (f['mensajero'], f['placa']))
        filas.sort(key=lambda f: f['fecha'], reverse=True)
        for f in filas:
            f['cumplimiento'] = cumplimiento(f['entregadas'], f['asignadas'])

        def totales(campo):
            grupos = {}
            for f in filas:
                g = grupos.get(f[campo])
                if g is None:
                    g = {campo: f[campo], '_dias': set(),
                         'despachos': 0, 'asignadas': 0, 'entregadas': 0, 'novedades': 0}
                    grupos[f[campo]] = g
                g['_dias'].add(f['fecha'])
                for c in ('despachos', 'asignadas', 'entregadas', 'novedades'):
                    g[c] += f[c]
            salida = []
            for g in sorted(grupos.values(), key=lambda x: x[campo]):
                g['dias'] = len(g.pop('_dias'))
                g['cumplimiento'] = cumplimiento(g['entregadas'], g['asignadas'])
                salida.append(g)
            return salida

        cols_num = [
            {'clave': 'despachos', 'titulo': 'Despachos', 'tipo': 'entero'},
            {'clave': 'asignadas', 'titulo': 'Asignadas', 'tipo': 'entero'},
            {'clave': 'entregadas', 'titulo': 'Entregadas', 'tipo': 'entero'},
            {'clave': 'novedades', 'titulo': 'Novedades', 'tipo': 'entero'},
            {'clave': 'cumplimiento', 'titulo': '% Cumplimiento', 'tipo': 'numero'},
        ]
        sumables = ['despachos', 'asignadas', 'entregadas', 'novedades']

        plantilla = ExcelPlantilla('Reporte por mensajero', _rango_texto(fecha_desde, fecha_hasta))
        plantilla.agregar_hoja(
            'Detalle diario',
            columnas=[
                {'clave': 'mensajero', 'titulo': 'Mensajero'},
                {'clave': 'placa', 'titulo': 'Placa'},
                {'clave': 'fecha', 'titulo': 'Fecha'},
            ] + cols_num,
            filas=filas,
            totales=sumables,
        )
        plantilla.agregar_hoja(
            'Totales por mensajero',
            columnas=[
                {'clave': 'mensajero', 'titulo': 'Mensajero'},
                {'clave': 'dias', 'titulo': 'Días', 'tipo': 'entero'},
            ] + cols_num,
            filas=totales('mensajero'),
            totales=sumables,
        )
        plantilla.agregar_hoja(
            'Totales por placa',
            columnas=[
                {'clave': 'placa', 'titulo': 'Placa'},
                {'clave': 'dias', 'titulo': 'Días', 'tipo': 'entero'},
            ] + cols_num,
            filas=totales('placa'),
            totales=sumables,
        )

        nombre = 'reporte_mensajero'
        if fecha_desde and fecha_hasta:
            nombre = f'{nombre}_{fecha_desde}_{fecha_hasta}'
        return plantilla.respuesta(f'{nombre}.xlsx')


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

        # Resumen por (mensajero x placa x zona) -> pago. Agregado en BD, completo.
        # Se incluye la placa porque un despacho puede no tener mensajero asignado
        # (conductor_id nulo) pero si vehiculo: sin la placa esas guias caerian en
        # "Sin asignar" sin forma de saber quien las hizo. Con la placa queda el
        # rastro del vehiculo para atribuir el pago o corregir la asignacion.
        resumen_bruto = list(
            visitas.values(
                'despacho__conductor_id', 'despacho__vehiculo__placa',
                'franja_id', 'franja_codigo',
            ).annotate(
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
                'placa': r['despacho__vehiculo__placa'],
                'zona_id': r['franja_id'],
                'zona_codigo': r['franja_codigo'],
                'zona_nombre': zonas.get(r['franja_id'], {}).get('nombre'),
                'asignadas': r['asignadas'],
                'entregadas': r['entregadas'],
                'novedades': r['novedades'],
            }
            for r in resumen_bruto
        ]

        if request.query_params.get('excel'):
            return self._exportar_excel(resumen, relacion, fecha_desde, fecha_hasta)

        return Response(
            {
                'relacion': relacion,
                'relacion_count': len(relacion),
                'truncado': truncado,
                'resumen': resumen,
            },
            status=status.HTTP_200_OK,
        )

    def _exportar_excel(self, resumen, relacion, fecha_desde, fecha_hasta):
        plantilla = ExcelPlantilla(
            'Entregas por zona (pago del mensajero)',
            _rango_texto(fecha_desde, fecha_hasta),
        )

        plantilla.agregar_hoja(
            'Resumen por zona',
            columnas=[
                {'clave': 'mensajero', 'titulo': 'Mensajero'},
                {'clave': 'placa', 'titulo': 'Placa'},
                {'clave': 'zona', 'titulo': 'Zona'},
                {'clave': 'zona_codigo', 'titulo': 'Código zona'},
                {'clave': 'asignadas', 'titulo': 'Asignadas', 'tipo': 'entero'},
                {'clave': 'entregadas', 'titulo': 'Entregadas', 'tipo': 'entero'},
                {'clave': 'novedades', 'titulo': 'Novedades', 'tipo': 'entero'},
            ],
            filas=[
                {
                    'mensajero': r['conductor_nombre'] or 'Sin asignar',
                    'placa': r['placa'] or 'Sin placa',
                    'zona': r['zona_nombre'] or 'Sin zona',
                    'zona_codigo': r['zona_codigo'] or '',
                    'asignadas': r['asignadas'],
                    'entregadas': r['entregadas'],
                    'novedades': r['novedades'],
                }
                for r in resumen
            ],
            totales=['asignadas', 'entregadas', 'novedades'],
        )

        plantilla.agregar_hoja(
            'Relación',
            columnas=[
                {'clave': 'fecha', 'titulo': 'Fecha', 'tipo': 'fecha'},
                {'clave': 'fecha_entrega', 'titulo': 'Fecha entrega', 'tipo': 'fecha'},
                {'clave': 'mensajero', 'titulo': 'Mensajero'},
                {'clave': 'placa', 'titulo': 'Placa'},
                {'clave': 'despacho_id', 'titulo': 'Despacho', 'tipo': 'entero'},
                {'clave': 'numero', 'titulo': 'Guía', 'tipo': 'entero'},
                {'clave': 'documento', 'titulo': 'Documento'},
                {'clave': 'destinatario', 'titulo': 'Destinatario'},
                {'clave': 'direccion', 'titulo': 'Dirección'},
                {'clave': 'zona', 'titulo': 'Zona'},
                {'clave': 'zona_codigo', 'titulo': 'Código zona'},
                {'clave': 'estado', 'titulo': 'Estado'},
            ],
            filas=[
                {
                    'fecha': e['fecha'],
                    'fecha_entrega': e['fecha_entrega'],
                    'mensajero': e['conductor_nombre'] or 'Sin asignar',
                    'placa': e['placa'] or 'Sin placa',
                    'despacho_id': e['despacho_id'],
                    'numero': e['numero'],
                    'documento': e['documento'],
                    'destinatario': e['destinatario'],
                    'direccion': e['destinatario_direccion'],
                    'zona': e['zona_nombre'] or 'Sin zona',
                    'zona_codigo': e['zona_codigo'] or '',
                    'estado': e['estado'],
                }
                for e in relacion
            ],
        )

        nombre = 'entregas_por_zona'
        if fecha_desde and fecha_hasta:
            nombre = f'{nombre}_{fecha_desde}_{fecha_hasta}'
        return plantilla.respuesta(f'{nombre}.xlsx')
