from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('dashboard.urls')),
    path('hydra/', include('hydra.urls')),
    path('frontal/', include('talos_frontal.urls')),
    path('reasoning/', include('talos_reasoning.urls')),
    path('environments/', include('environments.urls')),
    path('api-auth/', include('rest_framework.urls')),
]
