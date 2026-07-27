"""La orden de entrega (PDF) se genera sin reventar, con o sin empresa/logo.

Cubre el encabezado compartido (FormatoEncabezado): antes hacia
GenEmpresa.objects.get(pk=1) -> DoesNotExist si no habia empresa, y config()
reventaba si faltaba la env del logo. Ahora todo es best-effort.

Correr: python manage.py test ruteo.tests_orden_entrega_pdf
"""
from django_tenants.test.cases import TenantTestCase

from ruteo.formatos.orden_entrega import FormatoOrdenEntrega
from ruteo.models.despacho import RutDespacho
from ruteo.models.visita import RutVisita


class OrdenEntregaPdfTests(TenantTestCase):

    def test_pdf_valido_con_visita_y_sin_empresa(self):
        despacho = RutDespacho.objects.create()
        RutVisita.objects.create(
            despacho=despacho, ciudad_id=None, estado_despacho=True,
            destinatario='Cliente', destinatario_direccion='Calle 1',
        )
        pdf = FormatoOrdenEntrega().generar_pdf(despacho.id)
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertGreater(len(pdf), 500)

    def test_despacho_inexistente_no_revienta(self):
        pdf = FormatoOrdenEntrega().generar_pdf(999999)
        self.assertTrue(pdf.startswith(b'%PDF'))
