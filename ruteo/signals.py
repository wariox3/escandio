"""Señales que mantienen sincronizados los contadores de despacho.

Los contadores denormalizados (visitas / visitas_entregadas / visitas_novedad)
se mantenian a mano en decenas de sitios y se desincronizaban (daban
asignadas < entregadas y diferencias entre informes). Aqui se recomputan desde
las visitas reales ante cualquier guardado/borrado de una visita, para que no
puedan volver a driftear.

OJO: las operaciones masivas (bulk_update / QuerySet.update / .delete) NO
disparan estas señales; esos flujos llaman a DespachoServicio.recalcular_contadores
explicitamente.
"""
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from ruteo.models.visita import RutVisita
from ruteo.servicios.despacho import DespachoServicio


@receiver(pre_save, sender=RutVisita)
def _rutvisita_pre_save(sender, instance, **kwargs):
    # Se guarda el despacho anterior para poder recomputar AMBOS cuando la visita
    # se mueve de un despacho a otro (trasbordo, cambiar, retirar, liberar).
    if instance.pk:
        instance._despacho_contador_anterior = (
            RutVisita.objects.filter(pk=instance.pk).values_list('despacho_id', flat=True).first()
        )
    else:
        instance._despacho_contador_anterior = None


@receiver(post_save, sender=RutVisita)
def _rutvisita_post_save(sender, instance, **kwargs):
    DespachoServicio.recalcular_contadores(
        [instance.despacho_id, getattr(instance, '_despacho_contador_anterior', None)]
    )


@receiver(post_delete, sender=RutVisita)
def _rutvisita_post_delete(sender, instance, **kwargs):
    DespachoServicio.recalcular_contadores([instance.despacho_id])
