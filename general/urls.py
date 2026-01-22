from django.urls import path, include
from .views.prueba import PruebaView, enviar_coreo
from .views.predeterminado import PredeterminadoView
from .views.ciudad import CiudadViewSet
from .views.archivo import ArchivoViewSet
from .views.empresa import EmpresaViewSet
from .views.configuracion import ConfiguracionViewSet
from .views.complemento import ComplementoViewSet
from rest_framework import routers

router = routers.DefaultRouter()
router.register(r'ciudad', CiudadViewSet)
router.register(r'archivo', ArchivoViewSet)
router.register(r'empresa', EmpresaViewSet)
router.register(r'configuracion', ConfiguracionViewSet)
router.register(r'complemento', ComplementoViewSet)

urlpatterns = [    
    path('', include(router.urls)),
    path('funcionalidad/predeterminado/', PredeterminadoView.as_view(), name='general'),
    path('prueba/', PruebaView.as_view(), name='prueba'),
    path('prueba/enviar-correo/', enviar_coreo, name='prueba-enviar-correo')
]