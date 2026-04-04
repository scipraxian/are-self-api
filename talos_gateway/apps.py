"""Django app config for talos_gateway."""

from django.apps import AppConfig


class TalosGatewayConfig(AppConfig):
    """Configuration for the Talos gateway (Layer 4) app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'talos_gateway'
    verbose_name = 'Talos Gateway'
