from django.urls import re_path

from .dendrites import SynapticDendrite

websocket_urlpatterns = [
    re_path(
        r'^ws/synapse/(?P<receptor_class>\w+)/$',
        SynapticDendrite.as_asgi(),
    ),
]
