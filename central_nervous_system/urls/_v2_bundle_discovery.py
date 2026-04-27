"""V2 bundle URL discovery — internal helper for v2_urls.py.

Lives in its own module (rather than inside ``v2_urls.py`` itself) so
tests can ``from ._v2_bundle_discovery import _discover_bundle_routers``
without triggering ``v2_urls.py``'s module-import-time side effect (the
auto-call to ``_discover_bundle_routers(V2_CNS_ROUTER)`` at the bottom
of that file). Importing v2_urls.py at pytest *collection* time would
hit the DB before any ``django_db`` marker / fixture has unblocked it
under pytest-django.

In production, ``v2_urls.py`` imports this module and calls the
function at its own module-import time — same observable behaviour as
before, just with the function definition lifted out.
"""

import importlib
import logging

from django.db.utils import OperationalError, ProgrammingError
from rest_framework import routers

logger = logging.getLogger(__name__)


def _discover_bundle_routers(core_router: routers.SimpleRouter) -> None:
    """Mirror installed bundles' ``V2_GENOME_ROUTER`` into the core V2 router.

    Per the bundle URL convention: a bundle's entry module may ship a
    ``urls`` submodule exposing ``V2_GENOME_ROUTER`` (a
    ``routers.SimpleRouter()`` with viewsets registered). For every
    INSTALLED bundle, ensure its ``code/`` directory is on ``sys.path``,
    import ``<entry_module>.urls``, and extend ``core_router.registry``
    with the bundle's registered routes.

    Skip silently:
      * Neuroplasticity not importable / table not migrated (fresh DB).
      * Bundle's runtime dir missing (boot_bundles flips BROKEN
        elsewhere; URL discovery just steps past it here).
      * Bundle has no ``urls`` submodule (legit opt-out — data-only
        bundle).
      * ``urls`` module imports fine but exposes no
        ``V2_GENOME_ROUTER`` attribute (same opt-out shape).

    Raise loudly:
      * URL prefix collision against the core router or another bundle.
      * ``urls`` module exists but its own imports are broken (same
        shape as ``_boot_one``'s LOAD_FAILED branch — broken bundle
        code should not boot quietly).
    """
    # Defer the neuroplasticity imports — this helper is called from
    # v2_urls.py module-import (URL conf assembly) which must stay cheap.
    try:
        from neuroplasticity.loader import (
            _ensure_code_on_path,
            grafts_root,
            iter_installed_bundles,
        )
    except ImportError:
        logger.debug(
            '[v2_urls] neuroplasticity not importable; bundle URL '
            'discovery skipped.'
        )
        return

    runtime = grafts_root()
    if not runtime.exists():
        return

    try:
        bundles = list(iter_installed_bundles())
    except (OperationalError, ProgrammingError):
        # NeuralModifier table doesn't exist yet (initial migrate / fresh
        # DB). Mirror loader.boot_bundles' early-return shape.
        logger.debug(
            '[v2_urls] NeuralModifier table not ready; bundle URL '
            'discovery skipped.'
        )
        return

    existing_prefixes = {prefix for prefix, _, _ in core_router.registry}

    for modifier in bundles:
        bundle_dir = runtime / modifier.slug
        if not bundle_dir.exists():
            # Disk drift — boot_bundles handles BROKEN status; URL
            # discovery just steps past.
            continue

        manifest = modifier.manifest_json or {}
        entry_modules = manifest.get('entry_modules', [])
        if not entry_modules:
            continue

        _ensure_code_on_path(bundle_dir)

        for entry_module in entry_modules:
            urls_module_name = '%s.urls' % entry_module
            try:
                urls_module = importlib.import_module(urls_module_name)
            except ModuleNotFoundError as exc:
                # If the missing module IS the urls submodule we asked
                # for, the bundle simply has no urls.py — opt-out, skip.
                # If a transitively imported module is missing, urls.py
                # exists but its own imports are broken — raise loudly.
                if exc.name == urls_module_name:
                    continue
                raise

            bundle_router = getattr(urls_module, 'V2_GENOME_ROUTER', None)
            if bundle_router is None:
                # urls.py present but no router exported — opt-out.
                continue

            for prefix, viewset, basename in bundle_router.registry:
                if prefix in existing_prefixes:
                    raise RuntimeError(
                        '[v2_urls] URL prefix collision: bundle %r '
                        'tried to register prefix %r (basename %r); '
                        'prefix already present on the V2 router.'
                        % (modifier.slug, prefix, basename)
                    )
                core_router.registry.append((prefix, viewset, basename))
                existing_prefixes.add(prefix)
                logger.info(
                    '[v2_urls] Registered bundle route: '
                    'bundle=%s prefix=%s basename=%s',
                    modifier.slug, prefix, basename,
                )
