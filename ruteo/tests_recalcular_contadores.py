"""recalcular_contadores: repone los contadores de despacho desde las visitas.

Correr: python manage.py test ruteo.tests_recalcular_contadores
"""
from django_tenants.test.cases import TenantTestCase

from ruteo.management.commands.recalcular_contadores_despacho import recalcular_contadores
from ruteo.models.despacho import RutDespacho
from ruteo.models.visita import RutVisita


class RecalcularContadoresTests(TenantTestCase):

    def _visita(self, despacho, entregado=False, novedad=False):
        return RutVisita.objects.create(
            despacho=despacho, ciudad_id=None,
            estado_entregado=entregado, estado_novedad=novedad,
        )

    def test_corrige_contadores_drifteados(self):
        # Contadores MAL: asignadas(1) < entregadas(9).
        despacho = RutDespacho.objects.create(visitas=1, visitas_entregadas=9, visitas_novedad=5)
        self._visita(despacho, entregado=True)
        self._visita(despacho, entregado=True)
        self._visita(despacho, novedad=True)  # 3 reales: 2 entregadas, 1 novedad

        resultado = recalcular_contadores()

        self.assertEqual(len(resultado['corregidos']), 1)
        despacho.refresh_from_db()
        self.assertEqual(despacho.visitas, 3)
        self.assertEqual(despacho.visitas_entregadas, 2)
        self.assertEqual(despacho.visitas_novedad, 1)

    def test_dry_run_detecta_pero_no_escribe(self):
        despacho = RutDespacho.objects.create(visitas=5, visitas_entregadas=0, visitas_novedad=0)
        self._visita(despacho)  # 1 real, 0 entregada

        resultado = recalcular_contadores(dry_run=True)

        self.assertEqual(len(resultado['corregidos']), 1)
        despacho.refresh_from_db()
        self.assertEqual(despacho.visitas, 5)  # NO se escribio

    def test_no_toca_los_que_ya_estan_bien(self):
        despacho = RutDespacho.objects.create(visitas=2, visitas_entregadas=1, visitas_novedad=0)
        self._visita(despacho, entregado=True)
        self._visita(despacho)  # 2 reales: 1 entregada -> ya cuadra

        resultado = recalcular_contadores()

        self.assertEqual(resultado['corregidos'], [])
