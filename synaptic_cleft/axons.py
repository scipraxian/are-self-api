from django.urls import re_path

from .dendrites import SynapticDendrite

websocket_urlpatterns = [
    re_path(
        r'^ws/synapse/spike/(?P<spike_id>[0-9a-f-]+)/$',
        SynapticDendrite.as_asgi(),
    ),
]
