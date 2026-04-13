"""Django app config for talos_gateway."""

from django.apps import AppConfig


class AreSelfGatewayConfig(AppConfig):
    """Configuration for the Are-Self gateway app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'talos_gateway'
    verbose_name = 'Are-Self Gateway'

    def ready(self) -> None:
        import talos_gateway.signals  # noqa: F401
