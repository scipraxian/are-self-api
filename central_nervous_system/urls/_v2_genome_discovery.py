"""V2 genome URL discovery — internal helper for v2_urls.py.

Lives in its own module (rather than inside ``v2_urls.py`` itself) so
tests can ``from ._v2_genome_discovery import _discover_genome_routers``
without triggering ``v2_urls.py``'s module-import-time side effect (the
auto-call to ``_discover_genome_routers(V2_CNS_ROUTER)`` at the bottom
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


def _discover_genome_routers(core_router: routers.SimpleRouter) -> None:
    """Mirror installed genomes' ``V2_GENOME_ROUTER`` into the core V2 router.

    Per the genome URL convention: a genome's entry module may ship a
    ``urls`` submodule exposing ``V2_GENOME_ROUTER`` (a
    ``routers.SimpleRouter()`` with viewsets registered). For every
    INSTALLED genome, ensure its ``code/`` directory is on
    ``sys.path``, import ``<entry_module>.urls``, and extend
    ``core_router.registry`` with the genome's registered routes.

    Skip silently:
      * Neuroplasticity not importable / table not migrated (fresh DB).
      * Genome's graft dir missing (boot_genomes flips BROKEN
        elsewhere; URL discovery just steps past it here).
      * Genome has no ``urls`` submodule (legit opt-out — data-only
        genome).
      * ``urls`` module imports fine but exposes no
        ``V2_GENOME_ROUTER`` attribute (same opt-out shape).

    Raise loudly:
      * URL prefix collision against the core router or another genome.
      * ``urls`` module exists but its own imports are broken (same
        shape as ``_boot_one``'s LOAD_FAILED branch — broken genome
        code should not boot quietly).
    """
    # Defer the neuroplasticity imports — this helper is called from
    # v2_urls.py module-import (URL conf assembly) which must stay cheap.
    try:
        from neuroplasticity.loader import (
            _ensure_code_on_path,
            grafts_root,
            iter_installed_genomes,
        )
    except ImportError:
        logger.debug(
            '[v2_urls] neuroplasticity not importable; genome URL '
            'discovery skipped.'
        )
        return

    runtime = grafts_root()
    if not runtime.exists():
        return

    try:
        genomes = list(iter_installed_genomes())
    except (OperationalError, ProgrammingError):
        # NeuralModifier table doesn't exist yet (initial migrate / fresh
        # DB). Mirror loader.boot_genomes' early-return shape.
        logger.debug(
            '[v2_urls] NeuralModifier table not ready; genome URL '
            'discovery skipped.'
        )
        return

    existing_prefixes = {prefix for prefix, _, _ in core_router.registry}

    for modifier in genomes:
        graft_dir = runtime / modifier.slug
        if not graft_dir.exists():
            # Disk drift — boot_genomes handles BROKEN status; URL
            # discovery just steps past.
            continue

        manifest = modifier.manifest_json or {}
        entry_modules = manifest.get('entry_modules', [])
        if not entry_modules:
            continue

        _ensure_code_on_path(graft_dir)

        for entry_module in entry_modules:
            urls_module_name = '%s.urls' % entry_module
            try:
                urls_module = importlib.import_module(urls_module_name)
            except ModuleNotFoundError as exc:
                # If the missing module IS the urls submodule we asked
                # for, the genome simply has no urls.py — opt-out, skip.
                # If a transitively imported module is missing, urls.py
                # exists but its own imports are broken — raise loudly.
                if exc.name == urls_module_name:
                    continue
                raise

            genome_router = getattr(urls_module, 'V2_GENOME_ROUTER', None)
            if genome_router is None:
                # urls.py present but no router exported — opt-out.
                continue

            for prefix, viewset, basename in genome_router.registry:
                if prefix in existing_prefixes:
                    raise RuntimeError(
                        '[v2_urls] URL prefix collision: genome %r '
                        'tried to register prefix %r (basename %r); '
                        'prefix already present on the V2 router.'
                        % (modifier.slug, prefix, basename)
                    )
                core_router.registry.append((prefix, viewset, basename))
                existing_prefixes.add(prefix)
                logger.info(
                    '[v2_urls] Registered genome route: '
                    'genome=%s prefix=%s basename=%s',
                    modifier.slug, prefix, basename,
                )
