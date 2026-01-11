from django.apps import AppConfig


class TalosThalamusConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'talos_thalamus'

    def ready(self):
        import talos_thalamus.signals
