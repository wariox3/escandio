from django.urls import path, include
from .views.entrega import EntregaViewSet


from rest_framework import routers

router = routers.DefaultRouter()
router.register(r'entrega', EntregaViewSet)

urlpatterns = [    
    path('', include(router.urls)),
]