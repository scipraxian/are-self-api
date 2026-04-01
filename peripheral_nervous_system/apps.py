from django.apps import AppConfig


class PeripheralNervousSystemConfig(AppConfig):
    """AppConfig for the peripheral_nervous_system app."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'peripheral_nervous_system'

    def ready(self) -> None:
        import peripheral_nervous_system.celery_signals  # noqa: F401
