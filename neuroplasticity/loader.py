"""Contribution-aware NeuralModifier loader.

Pure-Python library called by the management commands and the AppConfig
boot hook. Manages the install / uninstall / enable / disable lifecycle
plus the boot-time hash-check + side-effect re-import pass.

Key invariants:

    * INSTALLED_APPS is never mutated. Bundles contribute data, not apps.
    * Every DB object created by `install_bundle` gets one
      NeuralModifierContribution row pointing at it via GenericForeignKey,
      so uninstall can walk the manifest in install order and delete
      cleanly.
    * The runtime tree at NEURAL_MODIFIERS_ROOT/<slug>/ is treated as
      derived state, never edited by hand. install copies into it,
      uninstall removes it.
    * Hash drift between the on-disk manifest and NeuralModifier.manifest_hash
      flips status to BROKEN and the bundle's entry modules are NOT imported.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import shutil
import sys
import traceback
from pathlib import Path
from typing import Iterable, Tuple

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core import serializers
from django.db import OperationalError, ProgrammingError, transaction

from .models import (
    NeuralModifier,
    NeuralModifierContribution,
    NeuralModifierInstallationEvent,
    NeuralModifierInstallationEventType,
    NeuralModifierInstallationLog,
    NeuralModifierStatus,
)

logger = logging.getLogger(__name__)

REQUIRED_MANIFEST_KEYS = (
    'slug',
    'name',
    'version',
    'author',
    'license',
    'entry_modules',
)


def modifier_genome_root() -> Path:
    """Source-of-truth directory for committed NeuralModifier bundles."""
    return Path(settings.MODIFIER_GENOME_ROOT)


def neural_modifiers_root() -> Path:
    """Runtime install directory (gitignored). Created on first install."""
    return Path(settings.NEURAL_MODIFIERS_ROOT)


def install_bundle(slug: str) -> NeuralModifier:
    """Copy a bundle to the runtime tree, import its code, load its data.

    Raises:
        FileNotFoundError: source `modifier_genome/<slug>/` is missing.
        FileExistsError: runtime `neural_modifiers/<slug>/` already exists.
        ValueError: manifest fails validation.
        Exception: re-raised after BROKEN flip if the entry module fails
            to import or modifier_data.json fails to deserialize.
    """
    source = modifier_genome_root() / slug
    if not source.exists():
        raise FileNotFoundError(
            '[Neuroplasticity] No bundle source at {0}.'.format(source)
        )

    manifest_path = source / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    _validate_manifest(manifest)
    manifest_hash = _compute_manifest_hash(manifest_path)

    modifier = _get_or_create_modifier(slug, manifest, manifest_hash)
    log = NeuralModifierInstallationLog.objects.create(
        neural_modifier=modifier,
        installation_manifest=manifest,
    )

    runtime = neural_modifiers_root() / slug
    if runtime.exists():
        raise FileExistsError(
            '[Neuroplasticity] Runtime dir exists at {0}; '
            'uninstall first.'.format(runtime)
        )

    contribution_count = 0
    try:
        runtime.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, runtime)
        _ensure_code_on_path(runtime)
        with transaction.atomic():
            _import_entry_modules(manifest['entry_modules'])
            contribution_count = _load_modifier_data(
                modifier, runtime / 'modifier_data.json'
            )
            modifier.status_id = NeuralModifierStatus.INSTALLED
            modifier.manifest_hash = manifest_hash
            modifier.manifest_json = manifest
            modifier.version = manifest.get('version', '')
            modifier.author = manifest.get('author', '')
            modifier.license = manifest.get('license', '')
            modifier.name = manifest.get('name', slug)
            modifier.save()
    except Exception:
        _remove_code_from_path(runtime)
        if runtime.exists():
            shutil.rmtree(runtime, ignore_errors=True)
        _log_event(
            log,
            NeuralModifierInstallationEventType.LOAD_FAILED,
            {'traceback': traceback.format_exc()},
        )
        modifier.status_id = NeuralModifierStatus.BROKEN
        modifier.save()
        logger.error(
            '[Neuroplasticity] Install failed for %s; flipped BROKEN.', slug
        )
        raise

    _log_event(
        log,
        NeuralModifierInstallationEventType.INSTALL,
        {
            'contributions': contribution_count,
            'manifest_hash': manifest_hash,
            'entry_modules': list(manifest['entry_modules']),
        },
    )
    logger.info(
        '[Neuroplasticity] Installed %s (%d contributions).',
        slug,
        contribution_count,
    )
    return modifier


def uninstall_bundle(slug: str) -> NeuralModifier:
    """Walk contributions in install order, delete targets, prune disk.

    The NeuralModifier row itself is preserved; status flips to DISCOVERED.
    """
    modifier = NeuralModifier.objects.get(slug=slug)
    log = NeuralModifierInstallationLog.objects.create(
        neural_modifier=modifier,
        installation_manifest=modifier.manifest_json,
    )

    contributions = list(modifier.contributions.order_by('created'))
    target_count = len(contributions)
    deleted = 0
    for contribution in contributions:
        target = contribution.content_object
        if target is not None:
            target.delete()
            deleted += 1
        contribution.delete()
    orphans = target_count - deleted

    runtime = neural_modifiers_root() / slug
    _remove_code_from_path(runtime)
    if runtime.exists():
        shutil.rmtree(runtime, ignore_errors=True)

    modifier.status_id = NeuralModifierStatus.DISCOVERED
    modifier.save()

    _log_event(
        log,
        NeuralModifierInstallationEventType.UNINSTALL,
        {
            'targets': target_count,
            'deleted': deleted,
            'orphans': orphans,
        },
    )
    logger.info(
        '[Neuroplasticity] Uninstalled %s (%d targets, %d orphans).',
        slug,
        deleted,
        orphans,
    )
    return modifier


def enable_bundle(slug: str) -> NeuralModifier:
    """Flip INSTALLED or DISABLED -> ENABLED. Emits an ENABLE event."""
    modifier = NeuralModifier.objects.get(slug=slug)
    modifier.status_id = NeuralModifierStatus.ENABLED
    modifier.save()
    log = modifier.current_installation()
    if log is not None:
        _log_event(
            log,
            NeuralModifierInstallationEventType.ENABLE,
            {'previous_status': 'enabled-flip'},
        )
    return modifier


def disable_bundle(slug: str) -> NeuralModifier:
    """Flip ENABLED -> DISABLED. Code stays on sys.path. DB stays intact."""
    modifier = NeuralModifier.objects.get(slug=slug)
    modifier.status_id = NeuralModifierStatus.DISABLED
    modifier.save()
    log = modifier.current_installation()
    if log is not None:
        _log_event(
            log,
            NeuralModifierInstallationEventType.DISABLE,
            {'previous_status': 'disabled-flip'},
        )
    return modifier


def iter_installed_bundles() -> Iterable[NeuralModifier]:
    """Yield every NeuralModifier whose status is INSTALLED or ENABLED."""
    return NeuralModifier.objects.filter(
        status_id__in=(
            NeuralModifierStatus.INSTALLED,
            NeuralModifierStatus.ENABLED,
        )
    )


def boot_bundles() -> None:
    """AppConfig.ready() hook. Re-imports entry modules; flips BROKEN on drift.

    Walks every directory under NEURAL_MODIFIERS_ROOT/. For each bundle whose
    NeuralModifier row exists and is INSTALLED/ENABLED, verifies manifest_hash
    matches disk, then puts code/ on sys.path and imports entry_modules.

    Does NOT re-load modifier_data.json. Data load only happens at install.

    Silently returns if the neuralmodifier table doesn't exist yet (pre-migrate
    state, e.g. inside `manage.py migrate` or test-DB setup).
    """
    runtime = neural_modifiers_root()
    if not runtime.exists():
        return

    try:
        bootable = list(iter_installed_bundles())
    except (OperationalError, ProgrammingError):
        logger.debug(
            '[Neuroplasticity] boot_bundles skipped — table not ready.'
        )
        return

    by_slug = {m.slug: m for m in bootable}

    for bundle_dir in sorted(runtime.iterdir()):
        if not bundle_dir.is_dir():
            continue
        modifier = by_slug.get(bundle_dir.name)
        if modifier is None:
            continue
        _boot_one(bundle_dir, modifier)


def _boot_one(bundle_dir: Path, modifier: NeuralModifier) -> None:
    manifest_path = bundle_dir / 'manifest.json'
    if not manifest_path.exists():
        _flip_broken_with_event(
            modifier,
            NeuralModifierInstallationEventType.HASH_MISMATCH,
            {'reason': 'manifest.json missing on disk'},
            installation_manifest=modifier.manifest_json,
        )
        return

    actual_hash = _compute_manifest_hash(manifest_path)
    if actual_hash != modifier.manifest_hash:
        _flip_broken_with_event(
            modifier,
            NeuralModifierInstallationEventType.HASH_MISMATCH,
            {'expected': modifier.manifest_hash, 'actual': actual_hash},
            installation_manifest=json.loads(manifest_path.read_text()),
        )
        return

    manifest = json.loads(manifest_path.read_text())
    _ensure_code_on_path(bundle_dir)
    try:
        _import_entry_modules(manifest['entry_modules'])
    except Exception:
        _flip_broken_with_event(
            modifier,
            NeuralModifierInstallationEventType.LOAD_FAILED,
            {'traceback': traceback.format_exc()},
            installation_manifest=manifest,
        )


def _get_or_create_modifier(
    slug: str, manifest: dict, manifest_hash: str
) -> NeuralModifier:
    """Reuse an existing row by slug, otherwise create one in DISCOVERED."""
    modifier = NeuralModifier.objects.filter(slug=slug).first()
    if modifier is not None:
        return modifier
    return NeuralModifier.objects.create(
        slug=slug,
        name=manifest.get('name', slug),
        version=manifest.get('version', ''),
        author=manifest.get('author', ''),
        license=manifest.get('license', ''),
        manifest_hash=manifest_hash,
        manifest_json=manifest,
        status_id=NeuralModifierStatus.DISCOVERED,
    )


def _validate_manifest(manifest: dict) -> None:
    missing = [k for k in REQUIRED_MANIFEST_KEYS if k not in manifest]
    if missing:
        raise ValueError(
            '[Neuroplasticity] Manifest missing required keys: {0}'.format(
                missing
            )
        )
    entry_modules = manifest['entry_modules']
    if not isinstance(entry_modules, list) or not all(
        isinstance(name, str) for name in entry_modules
    ):
        raise ValueError(
            '[Neuroplasticity] Manifest entry_modules must be a list of strings.'
        )


def _compute_manifest_hash(manifest_path: Path) -> str:
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def _ensure_code_on_path(bundle_runtime_dir: Path) -> None:
    code_dir = str((bundle_runtime_dir / 'code').resolve())
    if code_dir not in sys.path:
        sys.path.insert(0, code_dir)


def _remove_code_from_path(bundle_runtime_dir: Path) -> None:
    code_dir = str((bundle_runtime_dir / 'code').resolve())
    while code_dir in sys.path:
        sys.path.remove(code_dir)


def _import_entry_modules(entry_modules: Iterable[str]) -> None:
    """Re-import each entry module so side-effect registration re-fires."""
    for module_name in entry_modules:
        sys.modules.pop(module_name, None)
        importlib.import_module(module_name)


def _load_modifier_data(
    modifier: NeuralModifier, data_path: Path
) -> int:
    """Deserialize a bundle's modifier_data.json with contribution tracking.

    Each row is saved with its serialized PK preserved, then recorded as
    a NeuralModifierContribution row pointing back at the new object.
    """
    payload = data_path.read_text()
    count = 0
    for deserialized in serializers.deserialize('json', payload):
        deserialized.save()
        target = deserialized.object
        ct = ContentType.objects.get_for_model(type(target))
        NeuralModifierContribution.objects.create(
            neural_modifier=modifier,
            content_type=ct,
            object_id=target.pk,
        )
        count += 1
    return count


def _log_event(
    log: NeuralModifierInstallationLog,
    event_type_id: int,
    event_data: dict,
) -> NeuralModifierInstallationEvent:
    return NeuralModifierInstallationEvent.objects.create(
        neural_modifier_installation_log=log,
        event_type_id=event_type_id,
        event_data=event_data,
    )


def _flip_broken_with_event(
    modifier: NeuralModifier,
    event_type_id: int,
    event_data: dict,
    installation_manifest: dict,
) -> None:
    log = modifier.current_installation()
    if log is None:
        log = NeuralModifierInstallationLog.objects.create(
            neural_modifier=modifier,
            installation_manifest=installation_manifest,
        )
    _log_event(log, event_type_id, event_data)
    modifier.status_id = NeuralModifierStatus.BROKEN
    modifier.save()
    logger.warning(
        '[Neuroplasticity] %s flipped BROKEN: %s', modifier.slug, event_data
    )
