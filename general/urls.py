from django.urls import path, include
from .views.prueba import PruebaView, enviar_coreo, prueba_globalconnect_plantillas, prueba_globalconnect_enviar
from .views.predeterminado import PredeterminadoView
from .views.ciudad import CiudadViewSet
from .views.archivo import ArchivoViewSet
from .views.empresa import EmpresaViewSet
from .views.configuracion import ConfiguracionViewSet
from .views.complemento import ComplementoViewSet
from .views.api_key import ApiKeyViewSet
from rest_framework import routers

router = routers.DefaultRouter()
router.register(r'ciudad', CiudadViewSet)
router.register(r'archivo', ArchivoViewSet)
router.register(r'empresa', EmpresaViewSet)
router.register(r'configuracion', ConfiguracionViewSet)
router.register(r'complemento', ComplementoViewSet)
router.register(r'api-key', ApiKeyViewSet)

urlpatterns = [    
    path('', include(router.urls)),
    path('funcionalidad/predeterminado/', PredeterminadoView.as_view(), name='general'),
    path('prueba/', PruebaView.as_view(), name='prueba'),
    path('prueba/enviar-correo/', enviar_coreo, name='prueba-enviar-correo'),
    path('prueba/whatsapp/plantillas/', prueba_globalconnect_plantillas, name='prueba-whatsapp-plantillas'),
    path('prueba/whatsapp/enviar/', prueba_globalconnect_enviar, name='prueba-whatsapp-enviar'),
]