"""In-memory index of PKs that appear in any committed fixture file.

A "core row" is one whose ``genome`` FK is null AND whose PK shows up
in a fixture checked into the repo. An "orphan" is a null-genome row
whose PK is NOT in any fixture — the user forgot to tag it, and
saving the bundle would silently lose it.

The index is shaped::

    {"app_label.model": set(pks_that_appear_in_any_fixture)}

Built once at boot; rebuilt on ``post_migrate``. Exposed by the
Modifier Garden bundle-builder so the UI can render the fourth
diagnostic state alongside owned / shared / orphan.

API surface:

* :func:`get_fixture_pk_index` — cache-aware accessor. First call
  builds; subsequent calls hit the cached dict.
* :func:`refresh_fixture_pk_index` — force rebuild (post_migrate,
  on-demand).
* :func:`_build_fixture_pk_index` — pure builder, no cache side
  effects. Imported by tests.

Scans ``<app>/fixtures/initial_data.json`` for every app key in
``common.management.commands.core_dump.Command.TRANSACTIONAL_MODELS``
— that list is the canonical "apps whose structural rows are
dumped" set.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Dict, Set

from django.conf import settings

logger = logging.getLogger(__name__)

FIXTURE_FILENAME = 'initial_data.json'

_lock = threading.Lock()
_cache: Dict[str, Set[str]] | None = None


def _transactional_apps() -> list[str]:
    """The apps whose fixtures we scan.

    Sourced from ``core_dump``'s ``TRANSACTIONAL_MODELS`` dict keys —
    the same set the backup command writes ``initial_data.json`` for.
    """
    from common.management.commands.core_dump import Command as CoreDump

    return list(CoreDump.TRANSACTIONAL_MODELS.keys())


def _build_fixture_pk_index() -> Dict[str, Set[str]]:
    """Scan the fixture tree; return the index without touching the cache."""
    base_dir = Path(settings.BASE_DIR)
    index: Dict[str, Set[str]] = {}
    for app_label in _transactional_apps():
        fixture_path = (
            base_dir / app_label / 'fixtures' / FIXTURE_FILENAME
        )
        if not fixture_path.exists():
            continue
        try:
            payload = json.loads(fixture_path.read_text(encoding='utf-8'))
        except Exception as exc:
            logger.warning(
                '[Neuroplasticity] fixture_scan could not parse %s: %s',
                fixture_path,
                exc,
            )
            continue
        for row in payload:
            model_key = row.get('model')
            pk = row.get('pk')
            if not model_key or pk is None:
                continue
            index.setdefault(model_key, set()).add(str(pk))
    return index


def get_fixture_pk_index() -> Dict[str, Set[str]]:
    """Return the cached index, building on first access."""
    global _cache
    with _lock:
        if _cache is None:
            _cache = _build_fixture_pk_index()
        return _cache


def refresh_fixture_pk_index() -> Dict[str, Set[str]]:
    """Rebuild the cache from disk and return the fresh index."""
    global _cache
    new_index = _build_fixture_pk_index()
    with _lock:
        _cache = new_index
    return new_index


def clear_fixture_pk_index() -> None:
    """Drop the cache — tests use this to force a clean rebuild."""
    global _cache
    with _lock:
        _cache = None
