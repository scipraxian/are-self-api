from rest_framework import routers

from .api import DashboardViewSet

DASHBOARD_ROUTER = routers.SimpleRouter()
DASHBOARD_ROUTER.register(r'dashboard', DashboardViewSet, basename='dashboard')
