from django.contrib import admin
from django.urls import include, path
from rest_framework import routers

from environments.api_urls import ENVIRONMENTS_ROUTER
from hydra.api_urls import HYDRA_ROUTER

v1_router = routers.DefaultRouter()
v1_router.registry.extend(ENVIRONMENTS_ROUTER.registry)
v1_router.registry.extend(HYDRA_ROUTER.registry)
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('dashboard.urls')),
    path('hydra/', include('hydra.urls')),
    path('frontal/', include('talos_frontal.urls')),
    path('reasoning/', include('talos_reasoning.urls')),
    path('environments/', include('environments.urls')),
    path('api/v1/', include(v1_router.urls)),
    path('admin/', admin.site.urls),
    path(
        'api-auth/', include('rest_framework.urls', namespace='rest_framework')
    ),
]
