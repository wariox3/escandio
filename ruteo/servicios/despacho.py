from ruteo.models.visita import RutVisita
from ruteo.models.despacho import RutDespacho
from ruteo.models.novedad import RutNovedad
from ruteo.models.terminacion import RutTerminacion, RutTerminacionNovedad
from contenedor.models import User
from django.db import transaction, connection
from django.db.models import Count, Q
from django.utils import timezone

class DespachoServicio():

    # ------------------------------------------------------------------
    # Terminacion de viaje (Documento de Terminacion)
    # ------------------------------------------------------------------
    @staticmethod
    def validar_terminacion(despacho):
        """Reglas para poder terminar un viaje -> (ok, mensaje).

        Extraida de la vista terminar para que el preview y el cierre usen la
        MISMA validacion y no puedan divergir. Preserva los mensajes originales.
        """
        if despacho.estado_aprobado != True:
            return False, 'El despacho no esta aprobado'
        if despacho.estado_terminado != False:
            return False, 'El despacho ya esta terminado'
        pendientes = list(
            RutVisita.objects.filter(
                despacho_id=despacho.id, estado_entregado=False, estado_novedad=False
            ).values_list('numero', 'destinatario')
        )
        if pendientes:
            detalle = ', '.join(
                f'#{numero or "s/n"} {(destinatario or "").strip()}'.strip()
                for numero, destinatario in pendientes[:5]
            )
            if len(pendientes) > 5:
                detalle += f' y {len(pendientes) - 5} mas'
            return False, f'El despacho tiene {len(pendientes)} visita(s) sin entregar ni novedad: {detalle}'
        return True, ''

    @staticmethod
    def consolidado_viaje(despacho):
        """Consolidado del viaje para el documento de terminacion.

        Cuenta VISITAS REALES (no los contadores denormalizados). Estado final:
        'entregada' gana sobre 'novedad' -> con_novedad = novedad AND NOT
        entregada, asi entregadas + con_novedad + pendientes = total (mutuamente
        excluyentes). Una guia entregada que ademas tuvo novedad NO se lista como
        novedad (finalizo entregada).
        """
        visitas = RutVisita.objects.filter(despacho_id=despacho.id)
        total = visitas.count()
        entregadas = visitas.filter(estado_entregado=True).count()
        con_novedad_qs = visitas.filter(estado_novedad=True, estado_entregado=False)
        con_novedad = con_novedad_qs.count()
        porcentaje = round(entregadas / total * 100, 1) if total else 0

        # Detalle: la novedad mas reciente por visita, en UNA sola consulta (sin N+1).
        detalle = []
        visita_ids = list(con_novedad_qs.values_list('id', flat=True))
        if visita_ids:
            ultima_por_visita = {}
            for nov in (RutNovedad.objects
                        .filter(visita_id__in=visita_ids)
                        .select_related('novedad_tipo')
                        .order_by('visita_id', '-id')):
                ultima_por_visita.setdefault(nov.visita_id, nov)
            for v in con_novedad_qs.values('id', 'numero', 'destinatario').order_by('orden', 'id'):
                nov = ultima_por_visita.get(v['id'])
                detalle.append({
                    'numero': v['numero'],
                    'destinatario': v['destinatario'],
                    'tipo_novedad': nov.novedad_tipo.nombre if (nov and nov.novedad_tipo_id) else None,
                    'descripcion': nov.descripcion if nov else None,
                    'fecha': nov.fecha if nov else None,
                })

        conductor_nombre = None
        if despacho.conductor_id:
            u = User.objects.filter(pk=despacho.conductor_id).values('nombre', 'apellido').first()
            if u:
                conductor_nombre = f"{u['nombre'] or ''} {u['apellido'] or ''}".strip() or None

        # Agencia = contenedor (tenant actual). Consecutivo = nº de Orden de Entrega.
        agencia = getattr(getattr(connection, 'tenant', None), 'nombre', None)

        return {
            'despacho_id': despacho.id,
            'consecutivo': despacho.entrega_id,
            'agencia': agencia,
            'placa': despacho.vehiculo.placa if despacho.vehiculo_id else None,
            'conductor_id': despacho.conductor_id,
            'conductor_nombre': conductor_nombre,
            'fecha_viaje': despacho.fecha,
            'fecha_salida': despacho.fecha_salida,
            'total_guias': total,
            'entregadas': entregadas,
            'con_novedad': con_novedad,
            'porcentaje': porcentaje,
            'detalle_novedades': detalle,
        }

    @staticmethod
    def guardar_terminacion(despacho, consolidado, usuario_id=None):
        """Crea el snapshot inmutable del cierre desde el consolidado."""
        terminacion = RutTerminacion.objects.create(
            despacho=despacho,
            consecutivo=consolidado.get('consecutivo'),
            fecha_cierre=timezone.now(),
            usuario_id=usuario_id,
            agencia=consolidado.get('agencia'),
            placa=consolidado['placa'],
            conductor_nombre=consolidado['conductor_nombre'],
            fecha_viaje=consolidado['fecha_viaje'],
            fecha_salida=consolidado['fecha_salida'],
            total_guias=consolidado['total_guias'],
            entregadas=consolidado['entregadas'],
            con_novedad=consolidado['con_novedad'],
            porcentaje=consolidado['porcentaje'],
        )
        detalles = [
            RutTerminacionNovedad(
                terminacion=terminacion,
                numero=d['numero'],
                destinatario=d['destinatario'],
                tipo_novedad=d['tipo_novedad'],
                descripcion=d['descripcion'],
                fecha=d['fecha'],
            )
            for d in consolidado['detalle_novedades']
        ]
        if detalles:
            RutTerminacionNovedad.objects.bulk_create(detalles)
        return terminacion

    @staticmethod
    def recalcular_contadores(despacho_ids):
        """Repone visitas/visitas_entregadas/visitas_novedad contando las visitas
        reales de los despachos dados. Es la fuente unica de estos contadores:
        la llaman las señales de RutVisita (guardado/borrado) y, donde las señales
        no alcanzan (operaciones masivas o un save del despacho posterior al de la
        visita), se invoca explicito. Idempotente: solo escribe si algo cambia.
        NO toca visitas_liberadas (historico) ni los sumatorios (peso/volumen)."""
        if isinstance(despacho_ids, int):
            despacho_ids = [despacho_ids]
        ids = {i for i in despacho_ids if i}
        if not ids:
            return
        despachos = RutDespacho.objects.filter(pk__in=ids).annotate(
            _asignadas=Count('visitas_despacho_rel'),
            _entregadas=Count('visitas_despacho_rel', filter=Q(visitas_despacho_rel__estado_entregado=True)),
            _novedades=Count('visitas_despacho_rel', filter=Q(visitas_despacho_rel__estado_novedad=True)),
        ).only('id', 'visitas', 'visitas_entregadas', 'visitas_novedad')
        actualizar = []
        for d in despachos:
            if (d.visitas != d._asignadas
                    or d.visitas_entregadas != d._entregadas
                    or d.visitas_novedad != d._novedades):
                d.visitas = d._asignadas
                d.visitas_entregadas = d._entregadas
                d.visitas_novedad = d._novedades
                actualizar.append(d)
        if actualizar:
            RutDespacho.objects.bulk_update(
                actualizar, ['visitas', 'visitas_entregadas', 'visitas_novedad']
            )

    @staticmethod
    def regenerar_valores(despacho: RutDespacho):    
        visitas = RutVisita.objects.filter(despacho_id=despacho.id)
        despacho.peso=0
        despacho.volumen=0
        despacho.tiempo=0
        despacho.tiempo_servicio=0
        despacho.tiempo_trayecto=0
        despacho.visitas=0
        for visita in visitas:
            despacho.peso+=visita.peso
            despacho.volumen+=visita.volumen
            despacho.tiempo+=visita.tiempo
            despacho.tiempo_servicio+=visita.tiempo_servicio
            despacho.tiempo_trayecto+=visita.tiempo_trayecto
            despacho.visitas +=1
        despacho.save()

    @staticmethod
    def regenerar_indicador_entregas(despacho_id=None):    
        cantidad = 0
        parametro_despacho = ''
        if despacho_id:
            parametro_despacho = f' AND d.id = {despacho_id}'
        
        query = f'''
            SELECT
                d.id,
                d.visitas_entregadas,
                (SELECT COUNT(*) FROM rut_visita v WHERE v.despacho_id = d.id AND v.estado_entregado = true) AS visitas_entregadas_totales,
                (SELECT COUNT(*) FROM rut_visita v WHERE v.despacho_id = d.id) AS visitas_totales
            FROM
                rut_despacho d
            WHERE 
                d.estado_aprobado = true AND d.estado_terminado = false AND d.estado_anulado = false {parametro_despacho}
        '''        
        despachos_actualizar = []        
        with transaction.atomic():
            despachos_query = RutDespacho.objects.raw(query)
            for despacho_query in despachos_query:                
                despacho = RutDespacho.objects.get(id=despacho_query.id)      
                despacho.visitas_entregadas = despacho_query.visitas_entregadas_totales
                despacho.visitas = despacho_query.visitas_totales
                despachos_actualizar.append(despacho)
                cantidad += 1
            if despachos_actualizar:
                RutDespacho.objects.bulk_update(despachos_actualizar, ['visitas_entregadas', 'visitas'])  
        return cantidad 