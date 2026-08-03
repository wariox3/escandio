"""Documento de Terminacion de Viaje: validacion, consolidado, preview y snapshot.

Cubre:
- No-regresion de TERMINAR (mismas validaciones y efectos).
- Regla de "estado final" (una guia entregada que ademas tuvo novedad cuenta
  como entregada, no como novedad).
- El preview NO cambia estado.
- El snapshot es inmutable (no se recomputa tras el cierre).

Correr: python manage.py test ruteo.tests_terminacion
"""
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase

from contenedor.models import User
from ruteo.models.despacho import RutDespacho
from ruteo.models.novedad import RutNovedad
from ruteo.models.novedad_tipo import RutNovedadTipo
from ruteo.models.terminacion import RutTerminacion, RutTerminacionNovedad
from ruteo.models.vehiculo import RutVehiculo
from ruteo.models.visita import RutVisita
from ruteo.servicios.despacho import DespachoServicio
from ruteo.views.despacho import RutDespachoViewSet


class _User:
    def __init__(self, id=None):
        self.id = id


class _Req:
    def __init__(self, data, user_id=None):
        self.data = data
        self.user = _User(user_id)


class _Base(TenantTestCase):

    def setUp(self):
        super().setUp()
        self.tipo = RutNovedadTipo.objects.create(id=1, nombre='Dirección errada')
        self.vehiculo = RutVehiculo.objects.create(placa='ABC123', estado_asignado=True)
        self.despacho = RutDespacho.objects.create(
            estado_aprobado=True, vehiculo=self.vehiculo, conductor_id=None,
            fecha=timezone.now(), fecha_salida=timezone.now(),
        )

    def _visita(self, entregado=False, novedad=False, numero=None, destinatario='Cliente'):
        visita = RutVisita.objects.create(
            despacho=self.despacho, ciudad_id=None,
            estado_entregado=entregado, estado_novedad=novedad,
            numero=numero, destinatario=destinatario,
        )
        if novedad:
            RutNovedad.objects.create(
                fecha=timezone.now(), visita=visita, novedad_tipo=self.tipo,
                descripcion='No estaba el destinatario',
            )
        return visita


class ValidarTerminacionTests(_Base):

    def test_no_aprobado_bloquea(self):
        self.despacho.estado_aprobado = False
        self.despacho.save()
        ok, msg = DespachoServicio.validar_terminacion(self.despacho)
        self.assertFalse(ok)
        self.assertEqual(msg, 'El despacho no esta aprobado')

    def test_ya_terminado_bloquea(self):
        self.despacho.estado_terminado = True
        self.despacho.save()
        ok, msg = DespachoServicio.validar_terminacion(self.despacho)
        self.assertFalse(ok)
        self.assertEqual(msg, 'El despacho ya esta terminado')

    def test_pendientes_bloquea_con_detalle(self):
        self._visita(numero=7, destinatario='Ana')  # ni entregada ni novedad = pendiente
        ok, msg = DespachoServicio.validar_terminacion(self.despacho)
        self.assertFalse(ok)
        self.assertIn('1 visita(s) sin entregar ni novedad', msg)
        self.assertIn('#7 Ana', msg)

    def test_valido_pasa(self):
        self._visita(entregado=True)
        ok, msg = DespachoServicio.validar_terminacion(self.despacho)
        self.assertTrue(ok)


class ConsolidadoTests(_Base):

    def test_estado_final_entregada_gana_sobre_novedad(self):
        self._visita(entregado=True)                 # entregada
        self._visita(novedad=True, numero=2)         # con novedad (final)
        self._visita(entregado=True, novedad=True)   # entregada Y novedad -> cuenta entregada

        c = DespachoServicio.consolidado_viaje(self.despacho)

        self.assertEqual(c['total_guias'], 3)
        self.assertEqual(c['entregadas'], 2)         # las dos entregadas (incluida la que tuvo novedad)
        self.assertEqual(c['con_novedad'], 1)        # solo la de novedad-sin-entregar
        self.assertEqual(c['porcentaje'], 66.7)
        # entregadas + con_novedad = total (sin pendientes)
        self.assertEqual(c['entregadas'] + c['con_novedad'], c['total_guias'])
        # detalle: solo la guia #2, con su tipo
        self.assertEqual(len(c['detalle_novedades']), 1)
        self.assertEqual(c['detalle_novedades'][0]['numero'], 2)
        self.assertEqual(c['detalle_novedades'][0]['tipo_novedad'], 'Dirección errada')

    def test_detalle_usa_la_novedad_mas_reciente(self):
        visita = self._visita(novedad=True, numero=5)  # crea una novedad
        RutNovedadTipo.objects.create(id=2, nombre='Cliente ausente')
        RutNovedad.objects.create(
            fecha=timezone.now(), visita=visita, novedad_tipo_id=2, descripcion='reciente',
        )
        c = DespachoServicio.consolidado_viaje(self.despacho)
        self.assertEqual(c['detalle_novedades'][0]['tipo_novedad'], 'Cliente ausente')
        self.assertEqual(c['detalle_novedades'][0]['descripcion'], 'reciente')

    def test_conductor_nombre_se_resuelve(self):
        usuario = User.objects.create(username='c@x.com', correo='c@x.com', nombre='Juan', apellido='Perez')
        self.despacho.conductor_id = usuario.id
        self.despacho.save()
        self._visita(entregado=True)
        c = DespachoServicio.consolidado_viaje(self.despacho)
        self.assertEqual(c['conductor_nombre'], 'Juan Perez')
        self.assertEqual(c['placa'], 'ABC123')


class PreviewTests(_Base):

    def test_preview_no_cambia_estado(self):
        self._visita(entregado=True)
        respuesta = RutDespachoViewSet().terminar_preview(_Req({'id': self.despacho.id}))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['total_guias'], 1)
        self.despacho.refresh_from_db()
        self.assertFalse(self.despacho.estado_terminado)          # NO cerro
        self.assertFalse(RutTerminacion.objects.exists())         # NO creo snapshot

    def test_preview_bloqueado_devuelve_mismo_mensaje(self):
        self._visita(numero=9, destinatario='Luz')  # pendiente
        respuesta = RutDespachoViewSet().terminar_preview(_Req({'id': self.despacho.id}))
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('sin entregar ni novedad', respuesta.data['mensaje'])


class TerminarTests(_Base):

    def test_cierra_libera_vehiculo_y_crea_snapshot(self):
        self._visita(entregado=True)
        self._visita(novedad=True, numero=3)

        respuesta = RutDespachoViewSet().terminar(_Req({'id': self.despacho.id}, user_id=42))

        self.assertEqual(respuesta.status_code, 200)
        self.despacho.refresh_from_db()
        self.vehiculo.refresh_from_db()
        self.assertTrue(self.despacho.estado_terminado)           # cerro
        self.assertFalse(self.vehiculo.estado_asignado)           # libero vehiculo
        # snapshot correcto
        term = RutTerminacion.objects.get(despacho=self.despacho)
        self.assertEqual((term.total_guias, term.entregadas, term.con_novedad), (2, 1, 1))
        self.assertEqual(term.usuario_id, 42)
        self.assertEqual(term.placa, 'ABC123')
        self.assertEqual(RutTerminacionNovedad.objects.filter(terminacion=term).count(), 1)

    def test_snapshot_es_inmutable(self):
        self._visita(novedad=True, numero=1)         # 0 entregadas, 1 novedad
        RutDespachoViewSet().terminar(_Req({'id': self.despacho.id}))
        term = RutTerminacion.objects.get(despacho=self.despacho)
        self.assertEqual((term.entregadas, term.con_novedad), (0, 1))

        # Cambiar el estado de la visita DESPUES del cierre no debe alterar el snapshot.
        RutVisita.objects.filter(despacho=self.despacho).update(estado_entregado=True)
        term.refresh_from_db()
        self.assertEqual((term.entregadas, term.con_novedad), (0, 1))  # congelado

    def test_reterminar_no_duplica_snapshot(self):
        self._visita(entregado=True)
        RutDespachoViewSet().terminar(_Req({'id': self.despacho.id}))
        respuesta = RutDespachoViewSet().terminar(_Req({'id': self.despacho.id}))
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.data['mensaje'], 'El despacho ya esta terminado')
        self.assertEqual(RutTerminacion.objects.filter(despacho=self.despacho).count(), 1)


class TerminacionPdfTests(_Base):

    def test_pdf_valido_tras_terminar(self):
        self._visita(entregado=True)
        self._visita(novedad=True, numero=3)
        RutDespachoViewSet().terminar(_Req({'id': self.despacho.id}))
        respuesta = RutDespachoViewSet().terminacion_pdf(_Req({'id': self.despacho.id}))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertTrue(respuesta.content.startswith(b'%PDF'))

    def test_pdf_sin_snapshot_devuelve_400(self):
        respuesta = RutDespachoViewSet().terminacion_pdf(_Req({'id': self.despacho.id}))
        self.assertEqual(respuesta.status_code, 400)

    def test_pdf_sin_novedades_no_revienta(self):
        self._visita(entregado=True)  # 0 novedades -> "Sin guías con novedad"
        RutDespachoViewSet().terminar(_Req({'id': self.despacho.id}))
        respuesta = RutDespachoViewSet().terminacion_pdf(_Req({'id': self.despacho.id}))
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.content.startswith(b'%PDF'))
