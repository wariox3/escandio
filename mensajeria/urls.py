from django.urls import path, include
from rest_framework import routers
from mensajeria.views.webhook import webhook_whatsapp
from mensajeria.views.conexion import CtnWhatsappConexionViewSet
from mensajeria.views.conversacion import MsjConversacionViewSet

router = routers.DefaultRouter()
router.register(r'conexion', CtnWhatsappConexionViewSet, basename='mensajeria-conexion')
router.register(r'conversacion', MsjConversacionViewSet, basename='mensajeria-conversacion')

urlpatterns = [
    path('webhook/whatsapp/', webhook_whatsapp, name='mensajeria-webhook-whatsapp'),
    path('', include(router.urls)),
]
