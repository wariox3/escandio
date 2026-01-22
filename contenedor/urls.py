from django.urls import path, include
from .views.usuario import UsuarioViewSet
from .views.usuario_contenedor import UsuarioContenedorViewSet
from .views.contenedor import ContenedorViewSet
from rest_framework import routers

router = routers.DefaultRouter()
router.register(r'contenedor', ContenedorViewSet)
router.register(r'usuario', UsuarioViewSet, basename="usuario")
router.register(r'usuariocontenedor', UsuarioContenedorViewSet)

urlpatterns = [    
    path('', include(router.urls)),
]