"""Regresion: POST /ruteo/novedad/nuevo/ (contrato movil v1.6.4) no debe dar
500 opacos ("Servidor fuera de linea" -> bucle de auto-sync).

Cubre la misma clase de bug que ruteo/tests_entrega_idempotente.py, replicada
en el endpoint gemelo de novedades:

  - fecha malformada -> 400 controlado (no un 500 que el auto-sync reintenta
    en bucle). Antes strptime vivia dentro de transaction.atomic() y su
    ValueError se volvia 500.
  - fallo del complemento (HTTP externo) -> la novedad YA quedo registrada; su
    sincronizacion es best-effort y no debe tumbar la respuesta. Antes vivia
    dentro de la transaccion + lock.
  - reenvio con el mismo movil_token -> idempotente (mismo id, sin duplicar).

Correr: python manage.py test ruteo.tests_novedad_resiliente
"""
from unittest.mock import patch

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from rest_framework_simplejwt.tokens import RefreshToken

from contenedor.models import User
from general.models.configuracion import GenConfiguracion
from general.models.empresa import GenEmpresa
from ruteo.models.despacho import RutDespacho
from ruteo.models.novedad import RutNovedad
from ruteo.models.novedad_tipo import RutNovedadTipo
from ruteo.models.visita import RutVisita


class NovedadResilienteTests(TenantTestCase):

    def setUp(self):
        super().setUp()
        self.client = TenantClient(self.tenant)
        GenEmpresa.objects.get_or_create(
            pk=1,
            defaults={'nombre_corto': 'E', 'correo': 'e@x.com', 'contenedor_id': 1},
        )
        GenConfiguracion.objects.get_or_create(
            pk=1, defaults={'rut_sincronizar_complemento': False},
        )
        self.user = User.objects.create(
            username='cond.novedad@x.com', correo='cond.novedad@x.com',
            nombre='C', apellido='N', is_active=True,
        )
        self.token = str(RefreshToken.for_user(self.user).access_token)
        self.despacho = RutDespacho.objects.create(visitas=1, visitas_novedad=0)
        self.visita = RutVisita.objects.create(
            ciudad_id=None, despacho=self.despacho, estado_despacho=True,
        )
        self.tipo = RutNovedadTipo.objects.create(id=1, nombre='Cliente ausente')

    def _crear(self, fecha='2026-01-01 10:00', movil_token='tok-1'):
        return self.client.post(
            '/ruteo/novedad/nuevo/',
            {
                'visita_id': self.visita.id,
                'novedad_tipo_id': self.tipo.id,
                'fecha': fecha,
                'descripcion': 'no estaba',
                'movil_token': movil_token,
            },
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )

    @patch('ruteo.views.novedad.NotificacionServicio.notificar_visita_novedad')
    def test_fecha_invalida_responde_400_no_500(self, mock_notif):
        r = self._crear(fecha='no-es-fecha')
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(r.data['codigo'], 1)
        self.assertIn('fecha', r.data['mensaje'].lower())
        # No se creo ninguna novedad.
        self.assertEqual(RutNovedad.objects.count(), 0)

    @patch('ruteo.views.novedad.ComplementoServicio.enviar_novedad',
           side_effect=Exception('complemento caido'))
    @patch('ruteo.views.novedad.NotificacionServicio.notificar_visita_novedad')
    def test_fallo_del_complemento_no_tumba_la_novedad(self, mock_notif, mock_compl):
        GenConfiguracion.objects.filter(pk=1).update(rut_sincronizar_complemento=True)

        r = self._crear()

        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn('id', r.data)
        self.assertTrue(mock_compl.called)
        self.assertTrue(RutNovedad.objects.filter(pk=r.data['id']).exists())
        self.visita.refresh_from_db()
        self.assertTrue(self.visita.estado_novedad)
        self.despacho.refresh_from_db()
        self.assertEqual(self.despacho.visitas_novedad, 1)

    @patch('ruteo.views.novedad.NotificacionServicio.notificar_visita_novedad')
    def test_reenvio_mismo_movil_token_no_duplica(self, mock_notif):
        r1 = self._crear(movil_token='tok-dup')
        self.assertEqual(r1.status_code, 200, r1.content)
        r2 = self._crear(movil_token='tok-dup')
        self.assertEqual(r2.status_code, 200, r2.content)
        self.assertEqual(r1.data['id'], r2.data['id'])
        self.assertEqual(RutNovedad.objects.filter(movil_token='tok-dup').count(), 1)
        # El contador de novedades del despacho no se inflo con el reenvio.
        self.despacho.refresh_from_db()
        self.assertEqual(self.despacho.visitas_novedad, 1)
