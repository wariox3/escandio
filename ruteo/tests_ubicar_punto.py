"""Regresion: VisitaServicio.ubicar_punto no debe reventar (500) por una franja
con coordenadas nulas o malformadas.

Antes hacia `[(c['lng'], c['lat']) for c in franja.coordenadas]` sin proteger:
una franja creada pero NO dibujada tiene coordenadas=None -> `for c in None` ->
TypeError -> 500 en TODO lo que ubica (editar direccion, importar, rutear).

Correr: python manage.py test ruteo.tests_ubicar_punto
"""
from types import SimpleNamespace

from django.test import SimpleTestCase

from ruteo.servicios.visita import VisitaServicio


def _franja(coordenadas, id=1, codigo='Z1'):
    return SimpleNamespace(coordenadas=coordenadas, id=id, codigo=codigo)


# Cuadrado alrededor del origen (formato {lng, lat}).
CUADRO = [
    {'lng': -1, 'lat': -1}, {'lng': 1, 'lat': -1},
    {'lng': 1, 'lat': 1}, {'lng': -1, 'lat': 1},
]


class UbicarPuntoTests(SimpleTestCase):
    def test_franja_sin_coordenadas_no_revienta(self):
        self.assertFalse(VisitaServicio.ubicar_punto([_franja(None)], 0, 0)['encontrado'])

    def test_franja_lista_vacia_o_muy_corta_se_ignora(self):
        self.assertFalse(VisitaServicio.ubicar_punto([_franja([])], 0, 0)['encontrado'])
        self.assertFalse(
            VisitaServicio.ubicar_punto([_franja([{'lng': 0, 'lat': 0}])], 0, 0)['encontrado']
        )

    def test_franja_malformada_se_ignora(self):
        # 3 puntos pero les faltan claves lng/lat -> KeyError capturado, no crash.
        rota = _franja([{'lng': 0}, {'lat': 0}, {'x': 1}])
        self.assertFalse(VisitaServicio.ubicar_punto([rota], 0, 0)['encontrado'])

    def test_punto_dentro_del_poligono(self):
        r = VisitaServicio.ubicar_punto([_franja(CUADRO, codigo='DENTRO')], 0, 0)
        self.assertTrue(r['encontrado'])
        self.assertEqual(r['franja']['codigo'], 'DENTRO')

    def test_punto_fuera_del_poligono(self):
        self.assertFalse(VisitaServicio.ubicar_punto([_franja(CUADRO)], 5, 5)['encontrado'])

    def test_coordenadas_nulas_del_punto(self):
        self.assertFalse(VisitaServicio.ubicar_punto([_franja(CUADRO)], None, None)['encontrado'])

    def test_franja_rota_no_bloquea_a_la_buena(self):
        franjas = [_franja(None, codigo='ROTA'), _franja(CUADRO, codigo='BUENA')]
        r = VisitaServicio.ubicar_punto(franjas, 0, 0)
        self.assertTrue(r['encontrado'])
        self.assertEqual(r['franja']['codigo'], 'BUENA')
