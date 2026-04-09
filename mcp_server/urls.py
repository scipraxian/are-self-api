from django.urls import path

from mcp_server.django_bridge import mcp_endpoint

urlpatterns = [
    path('', mcp_endpoint, name='mcp-endpoint'),
]
