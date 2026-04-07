"""Django app config for auditory_cortex."""

from django.apps import AppConfig


class AuditoryCortexConfig(AppConfig):
    """Configuration for STT and auditory processing."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'auditory_cortex'
    verbose_name = 'Auditory Cortex'
