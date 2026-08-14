"""La orden de entrega (PDF) se genera sin reventar, con o sin empresa/logo.

Cubre el encabezado compartido (FormatoEncabezado): antes hacia
GenEmpresa.objects.get(pk=1) -> DoesNotExist si no habia empresa, y config()
reventaba si faltaba la env del logo. Ahora todo es best-effort.

Correr: python manage.py test ruteo.tests_orden_entrega_pdf
"""
from unittest.mock import patch

from django_tenants.test.cases import TenantTestCase

from ruteo.formatos.orden_entrega import FormatoOrdenEntrega, _numero_whatsapp_contenedor
from ruteo.models.despacho import RutDespacho
from ruteo.models.vehiculo import RutVehiculo
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

    def test_numero_whatsapp_none_sin_conexion(self):
        # Sin CtnWhatsappConexion activa en el tenant -> None (no se dibuja el banner).
        self.assertIsNone(_numero_whatsapp_contenedor())

    @patch('ruteo.formatos.orden_entrega._numero_whatsapp_contenedor', return_value='+57 300 123 4567')
    def test_pdf_con_banner_whatsapp_no_revienta(self, _num):
        # Con número y placa, el banner de "reportá por WhatsApp" se dibuja sin romper.
        vehiculo = RutVehiculo.objects.create(placa='ABC123', estado_asignado=True)
        despacho = RutDespacho.objects.create(vehiculo=vehiculo)
        RutVisita.objects.create(
            despacho=despacho, ciudad_id=None, estado_despacho=True,
            destinatario='Cliente', destinatario_direccion='Calle 1',
        )
        pdf = FormatoOrdenEntrega().generar_pdf(despacho.id)
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertGreater(len(pdf), 500)
