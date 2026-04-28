"""Pytest bootstrap — runs before Django setup.

Sets ``NEUROPLASTICITY_SKIP_BOOT=1`` so ``NeuroplasticityConfig.ready()``
does NOT connect ``request_started`` to ``boot_bundles()``. Without this,
the first ``APIClient`` call in any test fires ``boot_bundles()`` against
the *real* ``neuroplasticity/grafts/`` directory — its orphan sweep then
``rmtree``s every bundle dir lacking an INSTALLED row in the (test) DB.

Tests that legitimately need the boot pass call ``loader.boot_bundles()``
directly under ``override_settings(NEURAL_MODIFIER_GRAFTS_ROOT=...)``;
see ``test_modifier_lifecycle.py`` and ``test_install_unreal_bundle.py``.

Also sets ``ARE_SELF_SUPPRESS_RESTART=1`` so any unmocked code path that
reaches ``peripheral_nervous_system.autonomic_nervous_system.
trigger_system_restart`` short-circuits before the ``subprocess.Popen``
call that would spawn a real Celery worker and reload the live Daphne.
Tests that *assert* the restart still ``@patch`` the function — this is
defense-in-depth for any path that slips through.

``pytest_configure`` then wraps every loader mutation entry point with
an isolation guard. The wrap exists only when this conftest loads —
i.e. only under pytest — so the loader itself stays free of any
test-runner awareness. If a test reaches the loader without first
overriding ``NEURAL_MODIFIER_GRAFTS_ROOT`` /
``NEURAL_MODIFIER_GENOMES_ROOT`` to a tmp dir, the guarded wrapper
raises a loud ``RuntimeError`` naming the operation.
"""

import os

os.environ.setdefault('NEUROPLASTICITY_SKIP_BOOT', '1')
os.environ.setdefault('ARE_SELF_SUPPRESS_RESTART', '1')


def _install_loader_isolation_guard():
    """Wrap public ``neuroplasticity.loader`` entry points so a test
    that forgot to override the active grafts/genomes roots can't
    quietly mutate the user's checked-out bundle tree.

    Lives here, not in the loader, so production code stays free of
    pytest awareness. The wrap happens once at ``pytest_configure``
    time (after pytest-django runs ``django.setup()``); each guarded
    call resolves the active settings lazily so subsequent
    ``override_settings(...)`` blocks compose cleanly.
    """
    from functools import wraps
    from pathlib import Path

    from django.conf import settings
    from neuroplasticity import loader

    base = Path(settings.BASE_DIR)
    prod_grafts = (base / 'neuroplasticity' / 'grafts').resolve()
    prod_genomes = (base / 'neuroplasticity' / 'genomes').resolve()

    def _refuse(op, root_name, value):
        raise RuntimeError(
            '[Neuroplasticity loader isolation guard] REFUSING {0}: '
            '{1} resolves to the production path ({2}). The test '
            'that triggered this must override the setting to a tmp '
            'dir before calling into the loader.'.format(
                op, root_name, value,
            )
        )

    def _check(op, *, check_genomes):
        grafts = Path(settings.NEURAL_MODIFIER_GRAFTS_ROOT).resolve()
        if grafts == prod_grafts:
            _refuse(op, 'NEURAL_MODIFIER_GRAFTS_ROOT', grafts)
        if not check_genomes:
            return
        genomes = Path(settings.NEURAL_MODIFIER_GENOMES_ROOT).resolve()
        if genomes == prod_genomes:
            _refuse(op, 'NEURAL_MODIFIER_GENOMES_ROOT', genomes)

    def _wrap(name, *, check_genomes):
        original = getattr(loader, name)

        @wraps(original)
        def guarded(*args, **kwargs):
            _check(name, check_genomes=check_genomes)
            return original(*args, **kwargs)

        setattr(loader, name, guarded)

    _wrap('boot_bundles', check_genomes=False)
    _wrap('uninstall_bundle', check_genomes=False)
    _wrap('install_bundle_from_source', check_genomes=True)
    _wrap('install_bundle_from_archive', check_genomes=True)
    _wrap('upgrade_bundle_from_source', check_genomes=True)
    _wrap('upgrade_bundle', check_genomes=True)
    _wrap('save_bundle_to_archive', check_genomes=True)
    _wrap('create_empty_bundle', check_genomes=True)


def pytest_configure(config):
    _install_loader_isolation_guard()
