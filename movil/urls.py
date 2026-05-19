"""Rutas de la API movil v2, montadas en /api/v2/.

Ver movil/contrato_v2.py para el contrato que estas rutas deben respetar.
"""
from decouple import config
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import SimpleRouter

from movil.views.app import AppConfigView
from movil.views.auth import (
    LoginView,
    LogoutView,
    MeView,
    RegistroView,
    SolicitarClaveView,
    TokenRefreshMovilView,
)
from movil.views.despacho import DespachoMovilView, DespachosMiasView
from movil.views.novedad import NovedadMovilViewSet
from movil.views.ubicacion import UbicacionMovilView
from movil.views.visita import VisitaMovilViewSet

router = SimpleRouter()
router.register('visitas', VisitaMovilViewSet, basename='movil-visita')
router.register('novedades', NovedadMovilViewSet, basename='movil-novedad')

urlpatterns = [
    path('app/config/', AppConfigView.as_view(), name='movil-app-config'),
    path('auth/login/', LoginView.as_view(), name='movil-login'),
    path('auth/registro/', RegistroView.as_view(), name='movil-registro'),
    path('auth/token/refresh/', TokenRefreshMovilView.as_view(), name='movil-token-refresh'),
    path('auth/logout/', LogoutView.as_view(), name='movil-logout'),
    path('auth/me/', MeView.as_view(), name='movil-me'),
    path('auth/clave/solicitar/', SolicitarClaveView.as_view(), name='movil-clave-solicitar'),
    path('despachos/', DespachosMiasView.as_view(), name='movil-despachos-mias'),
    path('despachos/<int:pk>/', DespachoMovilView.as_view(), name='movil-despacho'),
    path('ubicacion/', UbicacionMovilView.as_view(), name='movil-ubicacion'),
    path('schema/', SpectacularAPIView.as_view(), name='schema-v2'),
]

# Swagger UI solo fuera de produccion.
if config('ENV', default='prod').lower() in ('dev', 'test', 'pruebas'):
    urlpatterns += [
        path(
            'schema/swagger/',
            SpectacularSwaggerView.as_view(url_name='schema-v2'),
            name='swagger-v2',
        ),
    ]

urlpatterns += router.urls
