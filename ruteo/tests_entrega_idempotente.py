"""Regresion: idempotencia de POST /ruteo/visita/entrega/ (contrato movil v1.6.4).

El auto-sync de la app re-envia automaticamente las entregas al reconectar, asi
que el mismo POST de entrega puede llegar dos (o mas) veces para la misma visita.
El endpoint debe ser idempotente:

  - reenvio SECUENCIAL (la respuesta del primer POST se perdio en la red): el
    chequeo `estado_entregado` lo cubre -> 200 sin duplicar nada.
  - reenvio CONCURRENTE (el segundo POST entra mientras el primero sigue dentro
    de la transaccion): lo cubre el lock de fila `select_for_update()` en
    entrega_action, que serializa ambos sobre la misma visita.

Ver el analisis en la nota de memoria 'entrega-idempotente-autosync' y
contenedor/contrato_movil.py.

Correr: python manage.py test ruteo.tests_entrega_idempotente
"""
import inspect
from unittest.mock import patch

from django.test import TestCase
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from rest_framework_simplejwt.tokens import RefreshToken

from contenedor.models import User
from general.models.archivo import GenArchivo
from general.models.configuracion import GenConfiguracion
from general.models.empresa import GenEmpresa
from ruteo.models.despacho import RutDespacho
from ruteo.models.visita import RutVisita
from ruteo.views.visita import RutVisitaViewSet


class EntregaIdempotenteTests(TenantTestCase):
    """Comportamiento observable: un reenvio NO duplica la entrega."""

    def setUp(self):
        super().setUp()
        self.client = TenantClient(self.tenant)
        # entrega_action lee GenConfiguracion(pk=1); a su vez exige GenEmpresa(pk=1).
        GenEmpresa.objects.get_or_create(
            pk=1,
            defaults={'nombre_corto': 'E', 'correo': 'e@x.com', 'contenedor_id': 1},
        )
        GenConfiguracion.objects.get_or_create(
            pk=1, defaults={'rut_sincronizar_complemento': False},
        )
        self.user = User.objects.create(
            username='cond.entrega@x.com', correo='cond.entrega@x.com',
            nombre='C', apellido='E', is_active=True,
        )
        self.token = str(RefreshToken.for_user(self.user).access_token)
        self.despacho = RutDespacho.objects.create(visitas=1, visitas_entregadas=0)
        self.visita = RutVisita.objects.create(
            ciudad_id=None, despacho=self.despacho, estado_despacho=True,
        )

    def _entregar(self):
        # Mismo payload que reenvia el auto-sync (sin idempotency key).
        return self.client.post(
            '/ruteo/visita/entrega/',
            {'id': self.visita.id, 'fecha_entrega': '2026-01-01 10:00'},
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )

    @patch('ruteo.views.visita.NotificacionServicio.notificar_visita_entregada')
    def test_reenvio_secuencial_no_duplica(self, mock_notif):
        r1 = self._entregar()
        self.assertEqual(r1.status_code, 200, r1.content)
        self.assertEqual(r1.data['mensaje'], 'Entrega con exito')

        # Segundo POST identico (la app creyo que el primero fallo).
        r2 = self._entregar()
        self.assertEqual(r2.status_code, 200, r2.content)
        self.assertEqual(r2.data['mensaje'], 'La visita ya estaba entregada')

        # Sin duplicar: contador del despacho incrementado UNA sola vez.
        self.despacho.refresh_from_db()
        self.assertEqual(self.despacho.visitas_entregadas, 1)

        self.visita.refresh_from_db()
        self.assertTrue(self.visita.estado_entregado)

        # Sin re-notificar al cliente: WhatsApp solo en la entrega real.
        self.assertEqual(mock_notif.call_count, 1)

        # Sin evidencias duplicadas (no se enviaron archivos en ningun POST).
        self.assertEqual(
            GenArchivo.objects.filter(modelo='RutVisita', codigo=self.visita.id).count(),
            0,
        )

    @patch('ruteo.views.visita.VisitaServicio.entrega_complemento',
           side_effect=Exception('complemento caido'))
    @patch('ruteo.views.visita.NotificacionServicio.notificar_visita_entregada')
    def test_fallo_del_complemento_no_tumba_la_entrega(self, mock_notif, mock_compl):
        # Con el complemento habilitado y CAIDO, la entrega ya quedo registrada
        # (commit hecho): su sincronizacion externa es best-effort y NO debe
        # devolver 500 ("Servidor fuera de linea") ni revertir la entrega. Antes
        # esta llamada vivia dentro de la transaccion + lock de fila.
        GenConfiguracion.objects.filter(pk=1).update(rut_sincronizar_complemento=True)

        r = self._entregar()

        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['mensaje'], 'Entrega con exito')
        self.assertTrue(mock_compl.called)  # se intento sincronizar
        self.visita.refresh_from_db()
        self.assertTrue(self.visita.estado_entregado)  # la entrega quedo firme
        self.despacho.refresh_from_db()
        self.assertEqual(self.despacho.visitas_entregadas, 1)

    @patch('ruteo.views.visita.NotificacionServicio.notificar_visita_entregada')
    def test_entrega_de_visita_ya_entregada_responde_200(self, mock_notif):
        # Visita marcada como entregada por fuera (p.ej. otra ruta/sync previo).
        self.visita.estado_entregado = True
        self.visita.save(update_fields=['estado_entregado'])
        r = self._entregar()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['mensaje'], 'La visita ya estaba entregada')
        self.despacho.refresh_from_db()
        self.assertEqual(self.despacho.visitas_entregadas, 0)  # no se toco el contador
        mock_notif.assert_not_called()


class EntregaLockGuardTests(TestCase):
    """Blindaje del fix de concurrencia: entrega_action DEBE tomar el lock de fila.

    El reenvio concurrente del auto-sync solo es seguro porque el chequeo de
    `estado_entregado` corre BAJO `select_for_update()`. Si alguien quita el lock
    (o saca el chequeo de dentro de la transaccion), se reabre la carrera que
    infla el contador y duplica fotos/WhatsApp. Este test lo detecta sin depender
    de un escenario multihilo flaky.
    """

    def test_entrega_action_usa_select_for_update(self):
        src = inspect.getsource(RutVisitaViewSet.entrega_action)
        self.assertIn(
            'select_for_update', src,
            'entrega_action debe obtener la visita con select_for_update() para '
            'serializar los reenvios concurrentes del auto-sync (ver '
            'ruteo/tests_entrega_idempotente.py).',
        )

    def test_chequeo_estado_entregado_esta_bajo_la_transaccion(self):
        # El lock solo sirve si el chequeo de idempotencia ocurre DENTRO de la
        # transaccion. Verificamos que el `with transaction.atomic()` aparece
        # antes del select_for_update y del chequeo de estado_entregado.
        src = inspect.getsource(RutVisitaViewSet.entrega_action)
        pos_atomic = src.find('transaction.atomic()')
        pos_lock = src.find('select_for_update')
        pos_check = src.find('estado_entregado ==')
        self.assertNotEqual(pos_atomic, -1)
        self.assertNotEqual(pos_lock, -1)
        self.assertNotEqual(pos_check, -1)
        self.assertLess(pos_atomic, pos_lock, 'el lock debe estar dentro de transaction.atomic()')
        self.assertLess(pos_lock, pos_check, 'el chequeo de estado debe ir despues de tomar el lock')
