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
        # Local import keeps the migrations path clean.
        from . import loader

        loader.boot_bundles()
