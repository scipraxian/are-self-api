"""Shared test helpers for NeuralModifier tests.

Exposes a cached extractor for the committed Unreal bundle zip so tests
that need the UE log-parser strategies registered can avoid a full
bundle install.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from django.conf import settings

_UNREAL_EXTRACTION: Optional[Path] = None


def ensure_unreal_bundle_code_on_path() -> Path:
    """Extract ``genomes/unreal.zip`` once per process; put its code on sys.path.

    Returns the extracted bundle directory. Idempotent: subsequent calls
    reuse the cached extraction. Tests that need UE log parsers or
    handlers registered (via their module-level
    ``LogParserFactory.register`` / ``register_native_handler`` calls)
    without running a full bundle install go through this helper.

    Callers must import the relevant module (e.g. ``are_self_unreal.log_parsers``)
    after this function returns; this helper only stages the path.
    """
    global _UNREAL_EXTRACTION
    if _UNREAL_EXTRACTION is not None and _UNREAL_EXTRACTION.exists():
        return _UNREAL_EXTRACTION

    archive_path = (
        Path(settings.BASE_DIR)
        / 'neuroplasticity'
        / 'genomes'
        / 'unreal.zip'
    )
    if not archive_path.exists():
        raise FileNotFoundError(
            '[Neuroplasticity/test_helpers] Cannot stage UE bundle: '
            'missing {0}.'.format(archive_path)
        )

    extraction_root = Path(tempfile.mkdtemp(prefix='are-self-ue-bundle-'))
    with zipfile.ZipFile(archive_path) as zf:
        zf.extractall(extraction_root)

    bundle_dir = extraction_root / 'unreal'
    code_dir = str((bundle_dir / 'code').resolve())
    if code_dir not in sys.path:
        sys.path.insert(0, code_dir)

    _UNREAL_EXTRACTION = bundle_dir
    return bundle_dir


def clear_unreal_bundle_extraction() -> None:
    """Tear down the cached extraction. Test hooks use this for isolation."""
    global _UNREAL_EXTRACTION
    if _UNREAL_EXTRACTION is None:
        return
    parent = _UNREAL_EXTRACTION.parent
    code_dir = str((_UNREAL_EXTRACTION / 'code').resolve())
    while code_dir in sys.path:
        sys.path.remove(code_dir)
    if parent.exists():
        shutil.rmtree(parent, ignore_errors=True)
    _UNREAL_EXTRACTION = None
