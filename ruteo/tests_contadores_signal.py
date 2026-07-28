"""Las señales de RutVisita mantienen los contadores del despacho sin drift.

Es la causa raiz: al crear/guardar/borrar/mover una visita, los contadores
(visitas / visitas_entregadas / visitas_novedad) se recomputan solos desde las
visitas reales, asi no pueden volver a driftear ni dar asignadas < entregadas.

Correr: python manage.py test ruteo.tests_contadores_signal
"""
from django_tenants.test.cases import TenantTestCase

from ruteo.models.despacho import RutDespacho
from ruteo.models.visita import RutVisita


class ContadoresSignalTests(TenantTestCase):

    def _visita(self, despacho, entregado=False, novedad=False):
        return RutVisita.objects.create(
            despacho=despacho, ciudad_id=None,
            estado_entregado=entregado, estado_novedad=novedad,
        )

    def _contadores(self, despacho):
        despacho.refresh_from_db()
        return (despacho.visitas, despacho.visitas_entregadas, despacho.visitas_novedad)

    def test_crear_visita_incrementa_asignadas(self):
        despacho = RutDespacho.objects.create()
        self._visita(despacho)
        self._visita(despacho)
        self.assertEqual(self._contadores(despacho), (2, 0, 0))

    def test_entregar_actualiza_entregadas(self):
        despacho = RutDespacho.objects.create()
        visita = self._visita(despacho)
        visita.estado_entregado = True
        visita.save()
        self.assertEqual(self._contadores(despacho), (1, 1, 0))

    def test_borrar_entregada_no_deja_asignadas_menor_que_entregadas(self):
        despacho = RutDespacho.objects.create()
        entregada = self._visita(despacho, entregado=True)
        self._visita(despacho, entregado=True)
        entregada.delete()
        visitas, entregadas, _ = self._contadores(despacho)
        self.assertEqual((visitas, entregadas), (1, 1))
        self.assertGreaterEqual(visitas, entregadas)

    def test_mover_visita_ajusta_ambos_despachos(self):
        origen = RutDespacho.objects.create()
        destino = RutDespacho.objects.create()
        visita = self._visita(origen, entregado=True)
        self._visita(origen)  # origen: 2 asignadas, 1 entregada

        visita.despacho = destino
        visita.save()

        self.assertEqual(self._contadores(origen), (1, 0, 0))
        self.assertEqual(self._contadores(destino), (1, 1, 0))
