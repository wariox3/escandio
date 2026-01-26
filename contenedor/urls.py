from django.urls import path, include
from .views.usuario import UsuarioViewSet
from .views.usuario_contenedor import UsuarioContenedorViewSet
from .views.contenedor import ContenedorViewSet
from .views.verificacion import VerificacionViewSet
from rest_framework import routers

router = routers.DefaultRouter()
router.register(r'contenedor', ContenedorViewSet)
router.register(r'usuario', UsuarioViewSet, basename="usuario")
router.register(r'usuariocontenedor', UsuarioContenedorViewSet)
router.register(r'verificacion', VerificacionViewSet)

urlpatterns = [    
    path('', include(router.urls)),
]