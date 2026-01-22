from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt import views as jwt_views
from rest_framework import permissions
from contenedor.views.seguridad import Login

urlpatterns = [
    path('admin/', admin.site.urls),
    path('ruteo/', include("ruteo.urls")),
    path('general/', include("general.urls")), 
    path('vertical/', include("vertical.urls")), 
    path('contenedor/', include("contenedor.urls")), 
    path('seguridad/login/', Login.as_view(), name='login'),
    path('seguridad/token/', jwt_views.TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('seguridad/token/refresh/', jwt_views.TokenRefreshView.as_view(), name='token_refresh'),
]
