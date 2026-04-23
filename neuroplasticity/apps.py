import os
import sys

from django.apps import AppConfig
from django.db.models.signals import post_migrate


class NeuroplasticityConfig(AppConfig):
    name = 'neuroplasticity'

    def ready(self):
        # post_migrate is always safe to wire — test runs, migrate, and
        # production all need a fresh fixture-scan rebuild after schema
        # work completes. The handler only touches disk.
        post_migrate.connect(
            _refresh_fixture_scan_on_migrate, sender=self
        )

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


def _refresh_fixture_scan_on_migrate(sender, **kwargs):
    from . import fixture_scan

    fixture_scan.refresh_fixture_pk_index()
