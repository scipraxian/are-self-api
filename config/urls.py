from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework import routers

from central_nervous_system.urls.api_urls import CNS_ROUTER
from central_nervous_system.urls.v2_urls import V2_CNS_ROUTER
from config.api_urls import CONFIG_URLS
from mcp_server.django_bridge import mcp_endpoint
from dashboard.api_urls import DASHBOARD_ROUTER
from environments.api_urls import ENVIRONMENTS_ROUTER
from frontal_lobe.api_urls import V2_REASONING_ROUTER
from hippocampus.api_urls import V2_HIPPOCAMPUS_ROUTER
from hypothalamus.api_urls import V2_HYPOTHALAMUS_ROUTER
from identity.api_urls import V2_IDENTITY_ROUTER
from neuroplasticity.api_urls import (
    NEUROPLASTICITY_V2_URLS,
    V2_NEUROPLASTICITY_ROUTER,
)
from parietal_lobe.api_urls import V2_PARIETAL_LOBE
from peripheral_nervous_system.api_urls import V2_PNS_ROUTER
from prefrontal_cortex.urls import V2_PREFRONTAL_CORTEX_ROUTER
from temporal_lobe.urls import V2_TEMPORAL_LOBE_ROUTER
from thalamus.urls import V2_THALAMUS

v1_router = routers.DefaultRouter()
v1_router.registry.extend(ENVIRONMENTS_ROUTER.registry)
v1_router.registry.extend(CNS_ROUTER.registry)
v1_router.registry.extend(DASHBOARD_ROUTER.registry)
v1_router.registry.extend(V2_REASONING_ROUTER.registry)


V2_ROUTER = routers.DefaultRouter()
V2_ROUTER.registry.extend(V2_CNS_ROUTER.registry)
V2_ROUTER.registry.extend(DASHBOARD_ROUTER.registry)
V2_ROUTER.registry.extend(V2_TEMPORAL_LOBE_ROUTER.registry)
V2_ROUTER.registry.extend(V2_IDENTITY_ROUTER.registry)
V2_ROUTER.registry.extend(V2_PREFRONTAL_CORTEX_ROUTER.registry)
V2_ROUTER.registry.extend(V2_HIPPOCAMPUS_ROUTER.registry)
V2_ROUTER.registry.extend(V2_REASONING_ROUTER.registry)
V2_ROUTER.registry.extend(V2_PARIETAL_LOBE.registry)
V2_ROUTER.registry.extend(V2_PNS_ROUTER.registry)
V2_ROUTER.registry.extend(V2_THALAMUS.registry)
V2_ROUTER.registry.extend(V2_HYPOTHALAMUS_ROUTER.registry)
V2_ROUTER.registry.extend(V2_NEUROPLASTICITY_ROUTER.registry)
V2_ROUTER.registry.extend(ENVIRONMENTS_ROUTER.registry)

urlpatterns = [
    path(
        'central_nervous_system/', include('central_nervous_system.urls.urls')
    ),
    path('api/v1/', include(v1_router.urls)),
    path('api/v2/', include(V2_ROUTER.urls)),
    path('api/v2/', include(CONFIG_URLS)),
    path('api/v2/', include(NEUROPLASTICITY_V2_URLS)),
    path('admin/', admin.site.urls),
    path(
        'api-auth/', include('rest_framework.urls', namespace='rest_framework')
    ),
    # Register both /mcp and /mcp/ — MCP clients hit either one, and
    # Django's APPEND_SLASH middleware can't redirect POSTs (it would lose
    # the request body). Explicit routes for both avoid the RuntimeError.
    path('mcp', mcp_endpoint, name='mcp-endpoint'),
    path('mcp/', mcp_endpoint, name='mcp-endpoint-slash'),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
