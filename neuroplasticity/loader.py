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
from django.db.models import Count
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

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


def catalog_root() -> Path:
    """On-disk catalog of installable NeuralModifier zip archives.

    Each ``*.zip`` under this directory is one bundle the user can
    install through the Modifier Garden. The directory is gitignored
    and treated as derived state — `pack_modifier` writes into it,
    `delete` action removes from it, install reads from it.
    """
    return Path(settings.NEURAL_MODIFIER_CATALOG_ROOT)


def read_archive_manifest(archive_path: Path) -> dict:
    """Read manifest.json from inside a bundle zip without extracting it.

    The zip's single top-level directory is the slug; we read
    ``<slug>/manifest.json`` from inside the archive. The manifest is
    the authority on what slug to call this bundle.

    Raises:
        ValueError: zip is empty, has multiple top-level dirs, or has
            no manifest.json at the slug path.
        zipfile.BadZipFile: the file isn't a valid zip.
    """
    import zipfile

    with zipfile.ZipFile(archive_path) as zf:
        names = zf.namelist()
        top = sorted({n.split('/', 1)[0] for n in names if n.strip('/')})
        if not top:
            raise ValueError(
                '[Neuroplasticity] Archive {0} is empty.'.format(archive_path)
            )
        if len(top) != 1:
            raise ValueError(
                '[Neuroplasticity] Archive {0} must contain a single '
                'top-level directory; got {1}.'.format(archive_path, top)
            )
        slug_dir = top[0]
        manifest_name = '{0}/manifest.json'.format(slug_dir)
        if manifest_name not in names:
            raise ValueError(
                '[Neuroplasticity] Archive {0} missing {1}.'.format(
                    archive_path, manifest_name
                )
            )
        return json.loads(zf.read(manifest_name).decode('utf-8'))


def read_catalog_manifests() -> list[dict]:
    """Walk the catalog dir; one entry per readable zip.

    Returns a list of ``{'manifest': dict, 'archive_path': str,
    'archive_name': str}``. A malformed zip or missing-manifest entry
    is logged and skipped — one bad zip never blanks the whole catalog.
    """
    root = catalog_root()
    if not root.exists():
        return []
    entries = []
    for archive_path in sorted(root.glob('*.zip')):
        try:
            manifest = read_archive_manifest(archive_path)
        except Exception as exc:
            logger.warning(
                '[Neuroplasticity] Skipping catalog entry %s: %s',
                archive_path.name,
                exc,
            )
            continue
        entries.append(
            {
                'manifest': manifest,
                'archive_path': str(archive_path),
                'archive_name': archive_path.name,
            }
        )
    return entries


def install_bundle(slug: str) -> NeuralModifier:
    """Install from the committed source at ``modifier_genome/<slug>/``.

    Thin wrapper around :func:`install_bundle_from_source` for the dev
    flow (``./manage.py build_modifier``). The API / catalog install
    path goes through :func:`install_bundle_from_archive` instead.

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
    return install_bundle_from_source(source, slug)


def install_bundle_from_source(source: Path, slug: str) -> NeuralModifier:
    """Copy ``source`` to the runtime tree, import its code, load its data.

    The source can be the committed ``modifier_genome/<slug>/`` (dev
    flow) or a transient extraction tempdir from a catalog zip — both
    look identical to this function.
    """
    manifest_path = source / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    _validate_manifest(manifest)
    _check_requires(manifest)
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
    """Walk contributions in reverse-install order, delete targets, prune disk.

    The NeuralModifier row itself is preserved; status flips to DISCOVERED.
    Reverse order unwinds intra-bundle FK chains: children (later-created)
    get deleted before parents (earlier-created), so PROTECT constraints
    inside the bundle's own graph don't trip.

    Event payload disambiguates three outcomes per contribution:

    * ``contributions_resolved``: target existed at snapshot time and is
      gone after the loop (deleted directly or via FK cascade — healthy).
    * ``orphaned_ids``: target was already missing at snapshot time
      (true orphan — out-of-band deletion before this uninstall).
    * ``contributions_unresolved``: target existed at snapshot time and
      somehow survived the loop. Should always be empty; a non-empty
      list means a bug to investigate.
    """
    modifier = NeuralModifier.objects.get(slug=slug)
    log = NeuralModifierInstallationLog.objects.create(
        neural_modifier=modifier,
        installation_manifest=modifier.manifest_json,
    )

    contributions = list(modifier.contributions.order_by('-created'))
    contributions_total = len(contributions)

    # Snapshot which targets exist NOW (before any deletion). FK cascade
    # during the loop will vanish dependent rows before the loop reaches
    # them — those are 'resolved', not 'orphaned'. Only targets missing
    # at snapshot time are real orphans.
    pre_existing: list[tuple[int, str]] = []
    pre_missing: list[str] = []
    for contribution in contributions:
        ct_id = contribution.content_type_id
        obj_id = str(contribution.object_id)
        model_cls = contribution.content_type.model_class()
        if model_cls is not None and model_cls._default_manager.filter(
            pk=contribution.object_id
        ).exists():
            pre_existing.append((ct_id, obj_id))
        else:
            pre_missing.append(obj_id)

    for contribution in contributions:
        target = contribution.content_object
        if target is not None:
            target.delete()
        contribution.delete()

    # Anything in pre_existing whose target row still survives is a bug.
    contributions_unresolved: list[str] = []
    for ct_id, obj_id in pre_existing:
        ct = ContentType.objects.get_for_id(ct_id)
        model_cls = ct.model_class()
        if model_cls is None:
            continue
        if model_cls._default_manager.filter(pk=obj_id).exists():
            contributions_unresolved.append(obj_id)

    contributions_resolved = len(pre_existing) - len(contributions_unresolved)

    runtime = neural_modifiers_root() / slug
    _remove_code_from_path(runtime)
    if runtime.exists():
        shutil.rmtree(runtime, ignore_errors=True)

    modifier.status_id = NeuralModifierStatus.DISCOVERED
    modifier.save()

    if contributions_unresolved:
        logger.warning(
            '[Neuroplasticity] Uninstall of %s left %d unresolved target(s): %s',
            slug,
            len(contributions_unresolved),
            contributions_unresolved,
        )

    _log_event(
        log,
        NeuralModifierInstallationEventType.UNINSTALL,
        {
            'contributions_total': contributions_total,
            'contributions_resolved': contributions_resolved,
            'orphaned_ids': pre_missing,
            'contributions_unresolved': contributions_unresolved,
        },
    )
    logger.info(
        '[Neuroplasticity] Uninstalled %s (%d resolved, %d orphaned, '
        '%d unresolved).',
        slug,
        contributions_resolved,
        len(pre_missing),
        len(contributions_unresolved),
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


def upgrade_bundle(
    slug: str, *, allow_same_version: bool = False
) -> dict:
    """Diff new modifier_data.json against current contributions; apply the delta.

    Returns a stats dict::

        {previous_version, new_version, created, updated, deleted}

    Raises:
        NeuralModifier.DoesNotExist: no bundle with that slug.
        FileNotFoundError: source bundle missing on disk.
        ValueError: manifest invalid, requires unmet, or new version
            <= old (unless allow_same_version).
    """
    modifier = NeuralModifier.objects.get(slug=slug)

    source = modifier_genome_root() / slug
    if not source.exists():
        raise FileNotFoundError(
            '[Neuroplasticity] No bundle source at {0}.'.format(source)
        )

    manifest_path = source / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    _validate_manifest(manifest)
    _check_requires(manifest)

    previous_version = modifier.version
    new_version = manifest['version']
    if not allow_same_version:
        if Version(new_version) <= Version(previous_version):
            raise ValueError(
                '[Neuroplasticity] Cannot upgrade {0}: on-disk {1} is not '
                'newer than installed {2}. Pass --allow-same-version to '
                'force.'.format(slug, new_version, previous_version)
            )

    new_manifest_hash = _compute_manifest_hash(manifest_path)
    log = NeuralModifierInstallationLog.objects.create(
        neural_modifier=modifier,
        installation_manifest=manifest,
    )

    runtime = neural_modifiers_root() / slug
    staging = runtime.with_suffix('.staging-upgrade')
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(source, staging)

    created = 0
    updated = 0
    deleted = 0
    try:
        new_payload = json.loads(
            (staging / 'modifier_data.json').read_text()
        )
        old_contributions_by_id = {
            str(c.object_id): c for c in modifier.contributions.all()
        }
        old_ids = set(old_contributions_by_id.keys())
        new_ids = {obj['pk'] for obj in new_payload}
        to_delete = old_ids - new_ids

        with transaction.atomic():
            for pk in to_delete:
                contribution = old_contributions_by_id[pk]
                target = contribution.content_object
                if target is not None:
                    target.delete()
                contribution.delete()
                deleted += 1

            raw = json.dumps(new_payload)
            for deserialized in serializers.deserialize('json', raw):
                pk = str(deserialized.object.pk)
                deserialized.save()
                if pk in old_ids:
                    updated += 1
                else:
                    ct = ContentType.objects.get_for_model(
                        type(deserialized.object)
                    )
                    NeuralModifierContribution.objects.create(
                        neural_modifier=modifier,
                        content_type=ct,
                        object_id=deserialized.object.pk,
                    )
                    created += 1

            _remove_code_from_path(runtime)
            if runtime.exists():
                shutil.rmtree(runtime)
            staging.rename(runtime)
            _ensure_code_on_path(runtime)
            _import_entry_modules(manifest['entry_modules'])

            modifier.version = new_version
            modifier.manifest_hash = new_manifest_hash
            modifier.manifest_json = manifest
            modifier.name = manifest.get('name', slug)
            modifier.author = manifest.get('author', '')
            modifier.license = manifest.get('license', '')
            modifier.save()
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        _log_event(
            log,
            NeuralModifierInstallationEventType.LOAD_FAILED,
            {'traceback': traceback.format_exc(), 'phase': 'upgrade'},
        )
        raise

    _log_event(
        log,
        NeuralModifierInstallationEventType.UPGRADE,
        {
            'previous_version': previous_version,
            'new_version': new_version,
            'created': created,
            'updated': updated,
            'deleted': deleted,
        },
    )
    logger.info(
        '[Neuroplasticity] Upgraded %s %s -> %s '
        '(created=%d updated=%d deleted=%d).',
        slug,
        previous_version,
        new_version,
        created,
        updated,
        deleted,
    )

    return {
        'previous_version': previous_version,
        'new_version': new_version,
        'created': created,
        'updated': updated,
        'deleted': deleted,
    }


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
    try:
        Version(manifest['version'])
    except InvalidVersion as exc:
        raise ValueError(
            '[Neuroplasticity] Manifest version {0!r} is not valid semver: '
            '{1}'.format(manifest['version'], exc)
        )
    _validate_requires(manifest.get('requires', []))


def _validate_requires(requires: list) -> None:
    if not isinstance(requires, list):
        raise ValueError(
            '[Neuroplasticity] Manifest "requires" must be a list.'
        )
    for entry in requires:
        if not isinstance(entry, dict):
            raise ValueError(
                '[Neuroplasticity] Each "requires" entry must be an object.'
            )
        if 'slug' not in entry or 'version_spec' not in entry:
            raise ValueError(
                '[Neuroplasticity] "requires" entry needs slug and '
                'version_spec.'
            )
        try:
            SpecifierSet(entry['version_spec'])
        except Exception as exc:
            raise ValueError(
                '[Neuroplasticity] Invalid version_spec {0!r}: {1}'.format(
                    entry['version_spec'], exc
                )
            )


def _check_requires(manifest: dict) -> None:
    """Raise ValueError if any declared requirement is unmet.

    Requirements resolve against installed NeuralModifier rows — DISCOVERED
    and BROKEN are treated as not-installed for this check.
    """
    requires = manifest.get('requires', [])
    if not requires:
        return
    installed = {
        m.slug: m
        for m in NeuralModifier.objects.filter(
            status_id__in=(
                NeuralModifierStatus.INSTALLED,
                NeuralModifierStatus.ENABLED,
                NeuralModifierStatus.DISABLED,
            )
        )
    }
    missing = []
    version_mismatches = []
    for req in requires:
        slug = req['slug']
        spec = SpecifierSet(req['version_spec'])
        other = installed.get(slug)
        if other is None:
            missing.append(slug)
            continue
        try:
            other_version = Version(other.version)
        except InvalidVersion:
            version_mismatches.append(
                '{0} installed with invalid version {1!r}'.format(
                    slug, other.version
                )
            )
            continue
        if other_version not in spec:
            version_mismatches.append(
                '{0} installed at {1}, need {2}'.format(
                    slug, other.version, spec
                )
            )
    if missing or version_mismatches:
        raise ValueError(
            '[Neuroplasticity] requires: not satisfied. '
            'missing={0} mismatches={1}'.format(missing, version_mismatches)
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


def install_bundle_from_archive(archive_path: Path) -> NeuralModifier:
    """Install a bundle from a zip already on disk in the catalog.

    Extracts the zip into a transient staging dir under
    ``neural_modifiers/_staging/<slug>/``, runs the normal install
    against the extraction, then nukes the staging dir on both success
    and failure. The zip stays where it was — it is the catalog entry.

    The zip must contain a single top-level directory; the manifest at
    ``<top>/manifest.json`` is the authority on the slug.

    Raises:
        ValueError: zip has bad shape or missing/invalid manifest.
        FileExistsError: a runtime dir for that slug already exists.
    """
    import zipfile

    archive_path = Path(archive_path)
    if not archive_path.exists():
        raise FileNotFoundError(
            '[Neuroplasticity] No catalog archive at {0}.'.format(archive_path)
        )

    manifest = read_archive_manifest(archive_path)
    slug = manifest.get('slug')
    if not slug:
        raise ValueError(
            '[Neuroplasticity] Archive {0} manifest is missing a slug.'.format(
                archive_path
            )
        )

    staging_parent = neural_modifiers_root() / '_staging'
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging_dir = staging_parent / slug
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)

    try:
        with zipfile.ZipFile(archive_path) as zf:
            top = sorted({n.split('/', 1)[0] for n in zf.namelist() if n.strip('/')})
            zf.extractall(staging_parent)
            extracted = staging_parent / top[0]
            if extracted != staging_dir:
                # Top-dir name in the zip differs from the manifest slug —
                # rename the extraction to the canonical slug-named dir.
                if staging_dir.exists():
                    shutil.rmtree(staging_dir, ignore_errors=True)
                shutil.move(str(extracted), str(staging_dir))
        return install_bundle_from_source(staging_dir, slug)
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)


def bundle_impact(slug: str) -> dict:
    """Contribution-count breakdown for a bundle, used by the uninstall preview.

    Returns::

        {
          'slug': str,
          'contribution_count': int,
          'breakdown': [{'content_type': 'app.model', 'count': N}, ...],
        }
    """
    modifier = NeuralModifier.objects.get(slug=slug)
    qs = (
        modifier.contributions
        .values('content_type__app_label', 'content_type__model')
        .annotate(count=Count('id'))
        .order_by('content_type__app_label', 'content_type__model')
    )
    breakdown = [
        {
            'content_type': '{0}.{1}'.format(
                row['content_type__app_label'], row['content_type__model']
            ),
            'count': row['count'],
        }
        for row in qs
    ]
    total = modifier.contributions.count()
    return {
        'slug': slug,
        'contribution_count': total,
        'breakdown': breakdown,
    }
