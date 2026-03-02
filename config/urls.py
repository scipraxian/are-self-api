from django.contrib import admin
from django.urls import include, path
from rest_framework import routers

from central_nervous_system.urls.api_urls import CNS_ROUTER
from central_nervous_system.urls.v2_urls import V2_CNS_ROUTER
from dashboard.api_urls import DASHBOARD_ROUTER
from environments.api_urls import ENVIRONMENTS_ROUTER
from frontal_lobe.api_urls import REASONING_ROUTER

v1_router = routers.DefaultRouter()
v1_router.registry.extend(ENVIRONMENTS_ROUTER.registry)
v1_router.registry.extend(CNS_ROUTER.registry)
v1_router.registry.extend(DASHBOARD_ROUTER.registry)
v1_router.registry.extend(REASONING_ROUTER.registry)


V2_ROUTER = routers.DefaultRouter()
V2_ROUTER.registry.extend(V2_CNS_ROUTER.registry)

urlpatterns = [
    path('', include('dashboard.urls')),
    path(
        'central_nervous_system/', include('central_nervous_system.urls.urls')
    ),
    path('environments/', include('environments.urls')),
    path('reasoning/', include('frontal_lobe.urls')),
    path('api/v1/', include(v1_router.urls)),
    path('api/v2/', include(V2_ROUTER.urls)),
    path('admin/', admin.site.urls),
    path(
        'api-auth/', include('rest_framework.urls', namespace='rest_framework')
    ),
    path('mcp/', include('djangorestframework_mcp.urls')),
]
