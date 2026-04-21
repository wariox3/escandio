from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt import views as jwt_views
from rest_framework import permissions
from contenedor.views.seguridad import Login, AdminLogin
from ruteo.views.externo import crear_guia, consultar_estado

urlpatterns = [
    path('admin/', admin.site.urls),
    path('ruteo/', include("ruteo.urls")),
    path('general/', include("general.urls")),
    path('vertical/', include("vertical.urls")),
    path('contenedor/', include("contenedor.urls")),
    path('mensajeria/', include("mensajeria.urls")),
    path('seguridad/login/', Login.as_view(), name='login'),
    path('seguridad/admin-login/', AdminLogin.as_view(), name='admin-login'),
    path('seguridad/token/', jwt_views.TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('seguridad/token/refresh/', jwt_views.TokenRefreshView.as_view(), name='token_refresh'),
    # API externa
    path('api/externo/guia/', crear_guia, name='api-externo-guia'),
    path('api/externo/guia/estado/', consultar_estado, name='api-externo-guia-estado'),
]
