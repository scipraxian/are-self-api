import os
import sys

from django.apps import AppConfig


class NeuroplasticityConfig(AppConfig):
    name = 'neuroplasticity'

    def ready(self):
        # Skip the boot pass during migrations, schema introspection, or
        # test collection — the neuralmodifier table may not exist yet,
        # and even if it does the test runner overrides settings paths.
        skip_argv_markers = (
            'migrate',
            'makemigrations',
            'collectstatic',
            'test',
        )
        if any(marker in sys.argv for marker in skip_argv_markers):
            return
        if os.environ.get('NEUROPLASTICITY_SKIP_BOOT'):
            return
        # Defer boot_bundles off AppConfig.ready() — the NeuralModifier
        # ORM query inside iter_installed_bundles() would otherwise trip
        # Django 6.x's "Accessing the database during app initialization
        # is discouraged" RuntimeWarning on every process start. The
        # boot module hooks request_started / worker_ready and runs the
        # bundle sweep on the first post-ready signal.
        from . import boot

        boot.schedule_boot()
