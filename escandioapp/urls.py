from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt import views as jwt_views
from rest_framework import permissions

urlpatterns = [
    path('admin/', admin.site.urls),
    path('ruteo/', include("ruteo.urls")),
    path('general/', include("general.urls")), 
    path('vertical/', include("vertical.urls")), 
]
