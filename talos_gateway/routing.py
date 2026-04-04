"""WebSocket URL routes for talos_gateway."""

from django.urls import path

from talos_gateway.stream_consumer import GatewayTokenStreamConsumer

websocket_urlpatterns = [
    path(
        'ws/gateway/stream/',
        GatewayTokenStreamConsumer.as_asgi(),
    ),
]
