from rest_framework import routers

from central_nervous_system.views.v2_viewsets import Pathway3DViewSet

V2_CNS_ROUTER = routers.SimpleRouter()
V2_CNS_ROUTER.register(r'pathways-3d', Pathway3DViewSet, basename='pathway-3d')
