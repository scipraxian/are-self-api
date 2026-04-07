"""Django app config for vocal_cortex."""

from django.apps import AppConfig


class VocalCortexConfig(AppConfig):
    """Configuration for TTS and voice profiles."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vocal_cortex'
    verbose_name = 'Vocal Cortex'
