from ruteo.models.visita import RutVisita
from ruteo.models.despacho import RutDespacho
from django.db import transaction
from django.db.models import Count, Q

class DespachoServicio():

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