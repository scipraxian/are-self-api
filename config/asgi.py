import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Initialize Django HTTP application early to ensure the AppRegistry is populated
django_asgi_app = get_asgi_application()

# Import your routing AFTER get_asgi_application() to avoid AppRegistryNotReady errors
import synaptic_cleft.axons

application = ProtocolTypeRouter(
    {
        # HTTP traffic goes to normal Django views
        'http': django_asgi_app,
        # WebSocket traffic goes through Channels
        'websocket': AuthMiddlewareStack(
            URLRouter(synaptic_cleft.axons.websocket_urlpatterns)
        ),
    }
)
