from django.apps import AppConfig


class CentralNervousSystemConfig(AppConfig):
    name = 'central_nervous_system'

    def ready(self):
        import central_nervous_system.signals
