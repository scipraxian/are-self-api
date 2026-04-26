"""NeuralModifier loader — genome-FK edition.

Pure-Python library called by the management commands and the AppConfig
boot hook. Manages the install / uninstall / create / save / upgrade
lifecycle plus the boot-time hash-check + side-effect re-import pass.

Layout invariants:

    * ``neuroplasticity/genomes/<slug>.zip`` is the single source of
      truth. A bundle exists iff its zip does. The zip is committed.
    * ``neuroplasticity/grafts/<slug>/`` is the runtime install tree.
      Gitignored, derived state; install copies into it, uninstall
      removes it.
    * ``neuroplasticity/operating_room/`` is the scratch space for
      transient install / upgrade / save extractions. Gitignored. Every
      operation creates a fresh ``tempfile.mkdtemp`` (or a fresh file)
      under this root and removes it in a ``finally`` block.

State invariants:

    * AVAILABLE = zip on disk, no DB row. Uninstall deletes the
      ``NeuralModifier`` row entirely. CASCADE handles owned rows,
      logs, and events.
    * INSTALLED_APPS is never mutated. Bundles contribute data, not apps.
    * Each DB object a bundle creates carries a ``genome`` FK (from
      ``GenomeOwnedMixin``). Uninstall = ``NeuralModifier.delete()``
      and CASCADE removes everything pointing at it.
    * Hash drift between the on-disk manifest and
      ``NeuralModifier.manifest_hash`` flips status to BROKEN and the
      bundle's entry modules are NOT imported.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import shutil
import sys
import tempfile
import traceback
import zipfile
from pathlib import Path
from typing import Iterable, Iterator, Optional

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.db import OperationalError, ProgrammingError, router, transaction
from django.db.models import PROTECT, RESTRICT
from django.db.models.deletion import Collector
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from neuroplasticity.genome_mixin import GenomeOwnedMixin

from .models import (
    NeuralModifier,
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


def grafts_root() -> Path:
    """Runtime install directory (gitignored). Created on first install."""
    return Path(settings.NEURAL_MODIFIER_GRAFTS_ROOT)


def genomes_root() -> Path:
    """On-disk collection of installable NeuralModifier zip archives.

    Each ``*.zip`` under this directory is one bundle the user can
    install through the Modifier Garden. The directory is committed to
    the repo — the zip IS the source of truth for its bundle.
    """
    return Path(settings.NEURAL_MODIFIER_GENOMES_ROOT)


def operating_room_root() -> Path:
    """Transient scratch root for install / upgrade / save operations."""
    return Path(settings.NEURAL_MODIFIER_OPERATING_ROOM_ROOT)


def iter_genome_owned_models() -> Iterator[type]:
    """Every concrete model that carries the ``genome`` FK.

    These are the twelve (and only twelve) models a ``NeuralModifier``
    can own rows in. Derived from ``GenomeOwnedMixin`` subclassing, so
    adding a thirteenth is a single-line mixin edit plus a migration —
    no registry edit here.
    """
    for model in apps.get_models():
        if issubclass(model, GenomeOwnedMixin):
            yield model


def _owned_delete_order() -> list[type]:
    """Topologically sort owned models for safe ``.delete()`` sequencing.

    A single ``modifier.delete()`` runs one giant CASCADE pass and
    Django's collector raises ``ProtectedError`` eagerly — it does NOT
    recognize that the PROTECT-source row is also scheduled for delete
    in the same pass. The fix is to delete owned rows per-model in an
    order that respects PROTECT / RESTRICT FKs between owned models:
    any model with a PROTECT FK pointing at another owned model is
    deleted first, so the PROTECT target is unreferenced when we get
    to it.
    """
    owned = list(iter_genome_owned_models())
    owned_set = set(owned)
    must_come_before = {m: set() for m in owned}
    for source_model in owned:
        for field in source_model._meta.fields:
            related = getattr(field, 'related_model', None)
            if related is None or related not in owned_set:
                continue
            if related is source_model:
                continue
            on_delete = field.remote_field.on_delete
            if on_delete in (PROTECT, RESTRICT):
                must_come_before[related].add(source_model)

    ordered: list[type] = []
    remaining = set(owned)
    while remaining:
        progress = False
        for model in list(remaining):
            if not (must_come_before[model] & remaining):
                ordered.append(model)
                remaining.remove(model)
                progress = True
        if not progress:
            ordered.extend(remaining)
            break
    return ordered


def read_archive_manifest(archive_path: Path) -> dict:
    """Read manifest.json from inside a bundle zip without extracting it."""
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
    """Walk the genomes dir; one entry per readable zip."""
    root = genomes_root()
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


def create_empty_bundle(
    slug: str,
    *,
    name: str = '',
    version: str = '0.1.0',
    author: str = '',
    license: str = '',
) -> NeuralModifier:
    """Scaffold a brand-new empty bundle.

    Creates ``grafts/<slug>/`` with an empty ``manifest.json``,
    ``modifier_data.json``, and ``code/`` dir, then registers a
    ``NeuralModifier`` row in INSTALLED state with no contributions.
    The user then stamps rows into it via the BEGIN_PLAY genome hook
    and packs the first archive via :func:`save_bundle_to_archive`.

    Refuses if the slug is already in use as an installed bundle, the
    runtime dir already exists, the catalog already has
    ``genomes/<slug>.zip``, or the slug is ``canonical``.
    """
    if slug == NeuralModifier.CANONICAL_SLUG:
        raise ValueError(
            '[Neuroplasticity] Cannot create a bundle named {0!r}.'.format(
                NeuralModifier.CANONICAL_SLUG
            )
        )
    if NeuralModifier.objects.filter(slug=slug).exists():
        raise FileExistsError(
            '[Neuroplasticity] Bundle {0!r} is already installed.'.format(slug)
        )
    catalog_archive = genomes_root() / '{0}.zip'.format(slug)
    if catalog_archive.exists():
        raise FileExistsError(
            '[Neuroplasticity] Catalog already has an archive at {0}; '
            'delete it first or pick a different slug.'.format(catalog_archive)
        )
    runtime = grafts_root() / slug
    if runtime.exists():
        raise FileExistsError(
            '[Neuroplasticity] Runtime dir already exists at {0}; '
            'uninstall first.'.format(runtime)
        )

    manifest = {
        'slug': slug,
        'name': name or slug,
        'version': version,
        'author': author,
        'license': license,
        'entry_modules': [],
        'requires': [],
    }
    _validate_manifest(manifest)

    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=False)
    (runtime / 'code').mkdir(parents=True, exist_ok=True)
    manifest_path = runtime / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    (runtime / 'modifier_data.json').write_text('[]\n')

    manifest_hash = _compute_manifest_hash(manifest_path)
    modifier = NeuralModifier.objects.create(
        slug=slug,
        name=manifest['name'],
        version=manifest['version'],
        author=manifest['author'],
        license=manifest['license'],
        manifest_hash=manifest_hash,
        manifest_json=manifest,
        status_id=NeuralModifierStatus.INSTALLED,
    )
    log = NeuralModifierInstallationLog.objects.create(
        neural_modifier=modifier,
        installation_manifest=manifest,
    )
    _log_event(
        log,
        NeuralModifierInstallationEventType.INSTALL,
        {
            'rows': 0,
            'manifest_hash': manifest_hash,
            'entry_modules': [],
            'created_empty': True,
        },
    )
    logger.info(
        '[Neuroplasticity] Created empty bundle %s (version %s).',
        slug,
        manifest['version'],
    )
    return modifier


def install_bundle_from_source(source: Path, slug: str) -> NeuralModifier:
    """Copy ``source`` to the runtime tree, import its code, load its data."""
    manifest_path = source / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    _validate_manifest(manifest)
    _check_requires(manifest)
    manifest_hash = _compute_manifest_hash(manifest_path)

    runtime = grafts_root() / slug
    if runtime.exists():
        raise FileExistsError(
            '[Neuroplasticity] Runtime dir exists at {0}; '
            'uninstall first.'.format(runtime)
        )

    pre_existing_row = NeuralModifier.objects.filter(slug=slug).exists()
    modifier = _get_or_create_modifier(slug, manifest, manifest_hash)
    if modifier.pk == NeuralModifier.CANONICAL:
        raise ValueError(
            '[Neuroplasticity] Refusing to install/upgrade onto the '
            'canonical modifier.'
        )
    log = NeuralModifierInstallationLog.objects.create(
        neural_modifier=modifier,
        installation_manifest=manifest,
    )

    row_count = 0
    try:
        runtime.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, runtime)
        _ensure_code_on_path(runtime)
        with transaction.atomic():
            _import_entry_modules(manifest['entry_modules'])
            row_count = _load_modifier_data(
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
        logger.error(
            '[Neuroplasticity] Install failed for %s; rolling back.', slug
        )
        if not pre_existing_row:
            modifier.delete()
        raise

    _log_event(
        log,
        NeuralModifierInstallationEventType.INSTALL,
        {
            'rows': row_count,
            'manifest_hash': manifest_hash,
            'entry_modules': list(manifest['entry_modules']),
        },
    )
    logger.info(
        '[Neuroplasticity] Installed %s (%d rows).',
        slug,
        row_count,
    )
    return modifier


def uninstall_bundle(slug: str) -> Optional[str]:
    """Drop owned rows in topological order, then delete the modifier row.

    AVAILABLE = no DB row. Ideally this would be a single
    ``modifier.delete()`` and CASCADE on every ``genome`` FK would
    clean up — but Django's collector raises ``ProtectedError`` eagerly
    whenever an in-pass PROTECT FK is seen, even when the PROTECT
    source is also scheduled for delete. So we delete owned rows
    per-model in an order that honours PROTECT/RESTRICT edges first,
    then the modifier itself (whose remaining CASCADEs only touch
    logs and events).

    Installation logs and events still cascade away with the modifier;
    this is consistent with "AVAILABLE means no DB footprint." Returns
    the deleted slug, or raises ``NeuralModifier.DoesNotExist`` if
    there is no row.

    Disk cleanup is intentionally deferred. On Windows, the current
    Daphne process has already imported the bundle's modules and holds
    live file handles, so ``shutil.rmtree`` silently no-ops and the
    runtime dir persists — which then blocks the next install with a
    ``FileExistsError``. Instead, ``uninstall_bundle`` only drops the
    code dir from ``sys.path`` (best effort; nothing else touches
    disk) and the API-level ``trigger_system_restart`` respawns
    Daphne. The orphan sweep in :func:`boot_bundles` does the real
    rmtree in the fresh process where no file locks remain.
    """
    modifier = NeuralModifier.objects.get(slug=slug)

    runtime = grafts_root() / slug
    _remove_code_from_path(runtime)

    with transaction.atomic():
        for model in _owned_delete_order():
            model.objects.filter(genome=modifier).delete()
        modifier.delete()
    logger.info('[Neuroplasticity] Uninstalled %s.', slug)
    return slug


def upgrade_bundle_from_source(
    source: Path, slug: str, *, allow_same_version: bool = False
) -> dict:
    """Diff new modifier_data.json against currently-owned rows; apply the delta.

    Returns::

        {previous_version, new_version, created, updated, deleted}

    Raises:
        NeuralModifier.DoesNotExist: no bundle with that slug.
        FileNotFoundError: source bundle missing on disk.
        ValueError: manifest invalid, requires unmet, or new version
            <= old (unless allow_same_version).
    """
    modifier = NeuralModifier.objects.get(slug=slug)
    if modifier.pk == NeuralModifier.CANONICAL:
        raise ValueError(
            '[Neuroplasticity] Refusing to install/upgrade onto the '
            'canonical modifier.'
        )

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

    runtime = grafts_root() / slug
    staging = runtime.with_suffix('.staging-upgrade')
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(source, staging)

    created = 0
    updated = 0
    deleted = 0
    try:
        new_payload = json.loads((staging / 'modifier_data.json').read_text())

        # Collect (model, pk) pairs the bundle currently owns across
        # every GenomeOwnedMixin-bearing model.
        old_pairs: set[tuple[type, str]] = set()
        for model in iter_genome_owned_models():
            for pk in model.objects.filter(genome=modifier).values_list(
                'pk', flat=True
            ):
                old_pairs.add((model, str(pk)))

        new_pairs: set[tuple[type, str]] = set()
        for row in new_payload:
            app_label, model_name = row['model'].split('.')
            model = apps.get_model(app_label, model_name)
            new_pairs.add((model, str(row['pk'])))

        to_delete = old_pairs - new_pairs
        new_pks_only = {pk for (_, pk) in new_pairs - old_pairs}

        with transaction.atomic():
            for model, pk in to_delete:
                model.objects.filter(pk=pk).delete()
                deleted += 1

            raw = json.dumps(new_payload)
            for deserialized in serializers.deserialize('json', raw):
                target = deserialized.object
                pk = str(target.pk)
                if isinstance(target, GenomeOwnedMixin):
                    _guard_install_collision(target, modifier)
                    target.genome_id = modifier.pk
                deserialized.save()
                if pk in new_pks_only:
                    created += 1
                else:
                    updated += 1

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


def upgrade_bundle(slug: str, *, allow_same_version: bool = False) -> dict:
    """Upgrade from the committed zip at ``genomes/<slug>.zip``."""
    archive_path = genomes_root() / '{0}.zip'.format(slug)
    if not archive_path.exists():
        raise FileNotFoundError(
            '[Neuroplasticity] No genome archive at {0}.'.format(archive_path)
        )

    operating_room_root().mkdir(parents=True, exist_ok=True)
    extraction = Path(tempfile.mkdtemp(dir=str(operating_room_root())))
    try:
        source = _extract_archive_into(archive_path, extraction, slug)
        return upgrade_bundle_from_source(
            source, slug, allow_same_version=allow_same_version
        )
    finally:
        if extraction.exists():
            shutil.rmtree(extraction, ignore_errors=True)


def _bump_patch_version(version: str) -> str:
    """Increment the semver patch of ``version``. Always returns a
    valid semver. Non-semver input is replaced with ``0.0.1`` rather
    than silently surviving as junk.
    """
    if not version:
        return '0.0.1'
    parts = version.split('.')
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        return '{0}.{1}.{2}'.format(major, minor, patch + 1)
    # Permissive fallback: bump from 0.0.0 rather than refusing the save.
    return '0.0.1'


def save_bundle_to_archive(slug: str) -> dict:
    """Serialize every bundle-owned row back into ``genomes/<slug>.zip``.

    The zip is built under ``operating_room/`` first, then atomically
    renamed over ``genomes/<slug>.zip`` — partial writes never land on
    disk. Includes manifest, modifier_data.json (the GenomeOwnedMixin
    rows filtered by ``genome=modifier`` PLUS the transit children of
    each owned NeuralPathway — Neurons / Axons / NeuronContexts —
    which compose the pathway but carry no ``genome`` FK of their
    own), and the bundle's live ``grafts/<slug>/code/`` tree.

    Always bumps the semver patch on save: the manifest's ``version``
    field is incremented, the new value is mirrored onto the
    ``NeuralModifier.version`` row, and the bumped manifest is what
    lands in the zip. This makes the saved archive ready for
    ``upgrade_bundle`` on another machine without an out-of-band
    version bump.

    Returns::

        {'slug', 'bytes_written', 'row_count', 'zip_path',
         'previous_version', 'new_version'}
    """
    import os
    import zipfile

    # Local imports — central_nervous_system / environments / parietal_lobe
    # depend on this app via the genome FK, so importing them at module
    # load risks circulars.
    from central_nervous_system.models import (
        Axon,
        Effector,
        EffectorArgumentAssignment,
        EffectorContext,
        NeuralPathway,
        Neuron,
        NeuronContext,
    )
    from environments.models import (
        ContextVariable,
        Executable,
        ExecutableArgumentAssignment,
        ProjectEnvironment,
    )
    from parietal_lobe.models import (
        ParameterEnum,
        ToolDefinition,
        ToolParameter,
        ToolParameterAssignment,
    )

    modifier = NeuralModifier.objects.get(slug=slug)

    rows: list = []
    row_count = 0
    for model in iter_genome_owned_models():
        qs = model.objects.filter(genome=modifier).order_by('pk')
        if not qs.exists():
            continue
        payload = json.loads(serializers.serialize('json', qs))
        for row in payload:
            # Strip the install-time genome FK — the consumer stamps it
            # at install time, so the value in the archive would just
            # point at a defunct NeuralModifier PK and confuse readers.
            row.get('fields', {}).pop('genome', None)
            rows.append(row)
            row_count += 1

    # Transit children of owned bundle parents. These rows are NOT
    # GenomeOwnedMixin — they don't carry a genome FK — but they
    # compose the bundle's content via their FK back to a bundle
    # parent. Without them, the saved bundle would land its owned
    # parents (pathways, effectors, etc.) as empty husks. Bundle
    # ownership is transitive via the FK chain. SpikeTrains / Spikes /
    # ReasoningSessions are intentionally excluded — they're runtime
    # telemetry, not bundle content. M2M through-tables (effector
    # switches, executable switches, engram_spikes) are serialized
    # implicitly as part of the parent row's M2M field list.
    owned_pathway_ids = list(
        NeuralPathway.objects.filter(genome=modifier).values_list(
            'pk', flat=True
        )
    )
    owned_effector_ids = list(
        Effector.objects.filter(genome=modifier).values_list('pk', flat=True)
    )
    owned_executable_ids = list(
        Executable.objects.filter(genome=modifier).values_list('pk', flat=True)
    )
    owned_environment_ids = list(
        ProjectEnvironment.objects.filter(genome=modifier).values_list(
            'pk', flat=True
        )
    )
    owned_tool_def_ids = list(
        ToolDefinition.objects.filter(genome=modifier).values_list(
            'pk', flat=True
        )
    )
    owned_tool_param_ids = list(
        ToolParameter.objects.filter(genome=modifier).values_list(
            'pk', flat=True
        )
    )

    transit_querysets: list = []
    if owned_pathway_ids:
        transit_querysets.append(
            Neuron.objects.filter(pathway_id__in=owned_pathway_ids).order_by(
                'pk'
            )
        )
        transit_querysets.append(
            Axon.objects.filter(pathway_id__in=owned_pathway_ids).order_by('pk')
        )
        owned_neuron_ids = list(
            Neuron.objects.filter(pathway_id__in=owned_pathway_ids).values_list(
                'pk', flat=True
            )
        )
        if owned_neuron_ids:
            transit_querysets.append(
                NeuronContext.objects.filter(
                    neuron_id__in=owned_neuron_ids
                ).order_by('pk')
            )
    if owned_effector_ids:
        transit_querysets.append(
            EffectorArgumentAssignment.objects.filter(
                effector_id__in=owned_effector_ids
            ).order_by('pk')
        )
        transit_querysets.append(
            EffectorContext.objects.filter(
                effector_id__in=owned_effector_ids
            ).order_by('pk')
        )
    if owned_executable_ids:
        transit_querysets.append(
            ExecutableArgumentAssignment.objects.filter(
                executable_id__in=owned_executable_ids
            ).order_by('pk')
        )
    if owned_environment_ids:
        transit_querysets.append(
            ContextVariable.objects.filter(
                environment_id__in=owned_environment_ids
            ).order_by('pk')
        )
    if owned_tool_def_ids:
        transit_querysets.append(
            ToolParameterAssignment.objects.filter(
                tool_id__in=owned_tool_def_ids
            ).order_by('pk')
        )
    if owned_tool_param_ids:
        transit_querysets.append(
            ParameterEnum.objects.filter(
                parameter_id__in=owned_tool_param_ids
            ).order_by('pk')
        )

    for qs in transit_querysets:
        if not qs.exists():
            continue
        payload = json.loads(serializers.serialize('json', qs))
        for row in payload:
            rows.append(row)
            row_count += 1

    runtime_bundle = grafts_root() / slug
    manifest_path = runtime_bundle / 'manifest.json'
    if manifest_path.exists():
        manifest_obj = json.loads(manifest_path.read_text())
    else:
        manifest_obj = dict(modifier.manifest_json or {})
        manifest_obj.setdefault('slug', modifier.slug)
        manifest_obj.setdefault('name', modifier.name)
        manifest_obj.setdefault('version', modifier.version)
        manifest_obj.setdefault('author', modifier.author)
        manifest_obj.setdefault('license', modifier.license)
        manifest_obj.setdefault('entry_modules', [])

    code_dir = runtime_bundle / 'code'

    # Pre-flight (FIRST — before any state mutation): refuse the save
    # if the manifest declares entry_modules but the runtime code tree
    # doesn't carry them. The earlier silent-broken-zip path overwrote
    # a working unreal.zip with a code-less archive because
    # grafts/<slug>/code/ was empty at save time. Catch that here
    # before bumping version, before any disk write, and before
    # touching the modifier row.
    declared_modules = list(manifest_obj.get('entry_modules', []))
    missing_modules = _missing_entry_modules(code_dir, declared_modules)
    if missing_modules:
        raise ValueError(
            '[Neuroplasticity] Refusing to save {0!r} - manifest declares '
            'entry_modules {1} but {2} cannot be located under {3}. Save '
            'would produce a code-less archive.'.format(
                slug, declared_modules, missing_modules, code_dir
            )
        )

    previous_version = manifest_obj.get('version', modifier.version or '0.0.0')
    new_version = _bump_patch_version(previous_version)
    manifest_obj['version'] = new_version
    manifest_text = json.dumps(manifest_obj, indent=2) + '\n'

    # Persist the bumped version onto the row + cached manifest_json so
    # subsequent reads don't drift from what the zip carries.
    modifier.version = new_version
    modifier.manifest_json = manifest_obj
    modifier.save(update_fields=['version', 'manifest_json'])

    operating_room_root().mkdir(parents=True, exist_ok=True)
    genomes_root().mkdir(parents=True, exist_ok=True)
    staging_fd, staging_name = tempfile.mkstemp(
        prefix='{0}-save-'.format(slug),
        suffix='.zip',
        dir=str(operating_room_root()),
    )
    os.close(staging_fd)
    staging_path = Path(staging_name)
    target = genomes_root() / '{0}.zip'.format(slug)
    backup_path: Optional[Path] = None
    try:
        with zipfile.ZipFile(staging_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('{0}/manifest.json'.format(slug), manifest_text)
            zf.writestr(
                '{0}/modifier_data.json'.format(slug),
                json.dumps(rows, indent=2) + '\n',
            )
            if code_dir.exists():
                for path in sorted(code_dir.rglob('*')):
                    if path.is_dir():
                        continue
                    arcname = Path(slug) / 'code' / path.relative_to(code_dir)
                    zf.write(path, arcname.as_posix())

        # Pre-flight: verify the staged zip is valid and contains the
        # declared entry_modules under the slug's code/ tree. Anything
        # the install side would later choke on must fail HERE, before
        # we replace the catalog target.
        _verify_staged_archive(staging_path, slug, declared_modules)

        # Backup the existing catalog zip before atomic replace. Single
        # rolling backup at <target>.bak — overwrites any prior backup.
        # This was Michael's standing rule after a save earlier today
        # silently destroyed a working unreal.zip: any modification to
        # a .zip must leave a backup as a programmatic effect.
        if target.exists():
            backup_path = target.with_suffix(target.suffix + '.bak')
            shutil.copy2(str(target), str(backup_path))

        os.replace(str(staging_path), str(target))
    except Exception:
        if staging_path.exists():
            staging_path.unlink()
        raise

    bytes_written = target.stat().st_size
    logger.info(
        '[Neuroplasticity] Saved %s to archive (%d rows, %d bytes, '
        'version %s -> %s).',
        slug,
        row_count,
        bytes_written,
        previous_version,
        new_version,
    )
    return {
        'slug': slug,
        'bytes_written': bytes_written,
        'row_count': row_count,
        'zip_path': str(target),
        'previous_version': previous_version,
        'new_version': new_version,
        'backup_path': str(backup_path) if backup_path else None,
    }


def _missing_entry_modules(code_dir: Path, entry_modules: list) -> list:
    """Return the subset of ``entry_modules`` not findable under
    ``code_dir`` as either ``<name>/__init__.py`` or ``<name>.py``.

    Empty list = all modules accounted for, save is safe to proceed.
    """
    missing: list = []
    if not entry_modules:
        return missing
    if not code_dir.exists():
        return list(entry_modules)
    for module_name in entry_modules:
        package_init = code_dir / module_name / '__init__.py'
        single_module = code_dir / '{0}.py'.format(module_name)
        if package_init.exists() or single_module.exists():
            continue
        missing.append(module_name)
    return missing


def _verify_staged_archive(
    staging_path: Path, slug: str, entry_modules: list
) -> None:
    """Re-open the staged zip with ``zipfile`` to confirm it's valid
    and that the declared entry_modules are present under
    ``<slug>/code/``. Raises ``ValueError`` on any failure — the caller
    is in a try/except that nukes the staged file before re-raising.
    """
    try:
        with zipfile.ZipFile(staging_path) as zf:
            names = set(zf.namelist())
    except zipfile.BadZipFile as exc:
        raise ValueError(
            '[Neuroplasticity] Staged archive failed re-open '
            'validation: {0}'.format(exc)
        )

    missing: list = []
    for module_name in entry_modules:
        package_init = '{0}/code/{1}/__init__.py'.format(slug, module_name)
        single_module = '{0}/code/{1}.py'.format(slug, module_name)
        if package_init in names or single_module in names:
            continue
        missing.append(module_name)
    if missing:
        raise ValueError(
            '[Neuroplasticity] Staged archive is missing entry_modules '
            '{0} under {1}/code/. Save aborted before catalog replace.'.format(
                missing, slug
            )
        )


def iter_installed_bundles() -> Iterable[NeuralModifier]:
    """Yield every NeuralModifier whose status is INSTALLED."""
    return NeuralModifier.objects.filter(
        status_id=NeuralModifierStatus.INSTALLED,
    )


def boot_bundles() -> None:
    """AppConfig-hook driven re-import pass; flips BROKEN on drift."""
    runtime = grafts_root()
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

    # Orphan sweep: remove any runtime dir that no longer has a DB
    # row. Uninstall defers disk cleanup to here so it runs in a
    # fresh process with empty sys.modules — Windows file locks from
    # the prior process are gone. Real rmtree, loud on failure.
    for bundle_dir in sorted(runtime.iterdir()):
        if not bundle_dir.is_dir() or bundle_dir.name in by_slug:
            continue
        try:
            logger.warning(
                '[Neuroplasticity] Orphan sweep about to remove %s; bootable=%s; stack:\n%s',
                bundle_dir,
                [m.slug for m in bootable],
                ''.join(traceback.format_stack()),
            )
            shutil.rmtree(bundle_dir)
            logger.info('[Neuroplasticity] Orphan sweep removed %s', bundle_dir)
        except Exception:
            logger.exception(
                '[Neuroplasticity] Orphan sweep failed for %s',
                bundle_dir,
            )

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
    """Reuse an existing row by slug, otherwise create one."""
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
        status_id=NeuralModifierStatus.INSTALLED,
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
    """Raise ValueError if any declared requirement is unmet."""
    requires = manifest.get('requires', [])
    if not requires:
        return
    installed = {
        m.slug: m
        for m in NeuralModifier.objects.filter(
            status_id=NeuralModifierStatus.INSTALLED,
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


def _load_modifier_data(modifier: NeuralModifier, data_path: Path) -> int:
    """Deserialize modifier_data.json; stamp ``genome`` on owned rows.

    Every row whose model inherits ``GenomeOwnedMixin`` gets
    ``genome_id`` set to the installing modifier's PK before save.
    Rows in other models (pure link tables, etc.) load as-is. The
    returned count is the total number of saved rows, regardless of
    ownership flag.

    Collision guard: for each GenomeOwnedMixin row, if the target PK
    already exists and is owned by canonical, another bundle, or a
    user (NULL), the install is refused with a clear error. Same-slug
    reinstalls are allowed through because the existing row's genome
    already points at this modifier. This stops the old
    silent-overwrite-and-stamp path that destroyed unrelated work
    when a bundle's PK happened to collide.
    """
    payload = data_path.read_text()
    count = 0
    for deserialized in serializers.deserialize('json', payload):
        target = deserialized.object
        if isinstance(target, GenomeOwnedMixin):
            _guard_install_collision(target, modifier)
            target.genome_id = modifier.pk
        deserialized.save()
        count += 1
    return count


def _guard_install_collision(
    target: 'GenomeOwnedMixin', modifier: NeuralModifier
) -> None:
    """Raise if ``target.pk`` is already owned by anyone but this bundle.

    Called per-row inside the install / upgrade deserialize loop.
    The existing row's ``genome_id`` decides the verdict:

    * matches the installing modifier — OK (same-slug reinstall /
      upgrade's own-row update).
    * equals ``NeuralModifier.CANONICAL`` — refuse. Bundles must not
      overwrite core-shipped rows.
    * equals ``NeuralModifier.INCUBATOR`` — refuse. Bundles must not
      overwrite rows the user created in the default workspace.
    * points at any other ``NeuralModifier`` — refuse. Bundles must
      not overwrite rows another bundle already owns.
    """
    model = type(target)
    existing_genome_id = (
        model.objects.filter(pk=target.pk)
        .values_list('genome_id', flat=True)
        .first()
    )
    if existing_genome_id is None:
        # genome is NOT NULL at the schema level, so a None result here
        # means the row itself is absent — fresh insert.
        return
    if existing_genome_id == modifier.pk:
        return
    if existing_genome_id == NeuralModifier.INCUBATOR:
        owner_label = 'user'
    elif existing_genome_id == NeuralModifier.CANONICAL:
        owner_label = repr(NeuralModifier.CANONICAL_SLUG)
    else:
        existing_slug = (
            NeuralModifier.objects.filter(pk=existing_genome_id)
            .values_list('slug', flat=True)
            .first()
        )
        owner_label = repr(existing_slug) if existing_slug else 'unknown-bundle'

    raise RuntimeError(
        '[Neuroplasticity] Refusing to overwrite {0}.{1} PK {2} owned '
        'by {3} while installing {4!r}.'.format(
            model._meta.app_label,
            model._meta.model_name,
            target.pk,
            owner_label,
            modifier.slug,
        )
    )


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


def _extract_archive_into(
    archive_path: Path, extraction_dir: Path, slug: str
) -> Path:
    """Extract ``archive_path`` into ``extraction_dir`` and return the slug dir."""
    import zipfile

    with zipfile.ZipFile(archive_path) as zf:
        top = sorted(
            {n.split('/', 1)[0] for n in zf.namelist() if n.strip('/')}
        )
        zf.extractall(extraction_dir)

    extracted = extraction_dir / top[0]
    slug_dir = extraction_dir / slug
    if extracted != slug_dir:
        if slug_dir.exists():
            shutil.rmtree(slug_dir, ignore_errors=True)
        shutil.move(str(extracted), str(slug_dir))
    return slug_dir


def install_bundle_from_archive(archive_path: Path) -> NeuralModifier:
    """Install a bundle from a zip on disk."""
    archive_path = Path(archive_path)
    if not archive_path.exists():
        raise FileNotFoundError(
            '[Neuroplasticity] No genome archive at {0}.'.format(archive_path)
        )

    manifest = read_archive_manifest(archive_path)
    slug = manifest.get('slug')
    if not slug:
        raise ValueError(
            '[Neuroplasticity] Archive {0} manifest is missing a slug.'.format(
                archive_path
            )
        )

    operating_room_root().mkdir(parents=True, exist_ok=True)
    extraction = Path(tempfile.mkdtemp(dir=str(operating_room_root())))
    try:
        source = _extract_archive_into(archive_path, extraction, slug)
        return install_bundle_from_source(source, slug)
    finally:
        if extraction.exists():
            shutil.rmtree(extraction, ignore_errors=True)


def bundle_uninstall_preview(slug: str) -> dict:
    """Full cascade tree for an uninstall, built via ``Collector.collect()``.

    Gathers every row the bundle directly owns (``genome=modifier`` across
    the GenomeOwnedMixin consumers), feeds them into a
    ``django.db.models.deletion.Collector`` — the same collector Django
    admin uses for its delete-confirmation page — and returns the walked
    tree as::

        {
          'slug': str,
          'row_count': int,
          'direct':    [{...}, ...],  # rows the bundle owns
          'cascade':   [{...}, ...],  # rows CASCADE removes with them
          'set_null':  [{...}, ...],  # rows whose FK gets nulled
          'protected': [{...}, ...],  # rows that would PROTECT-block
        }

    Each entry is ``{app_label, model, pk, name_or_repr, reason}``.
    The UI renders the full tree in the confirmation dialog — Michael's
    explicit ask: show, like Django admin does.
    """
    modifier = NeuralModifier.objects.get(slug=slug)

    direct_keys: set = set()
    per_model: dict = {}
    for model in iter_genome_owned_models():
        bucket = list(model.objects.filter(genome=modifier))
        if not bucket:
            continue
        per_model[model] = bucket
        for obj in bucket:
            direct_keys.add((type(obj), obj.pk))

    collector = Collector(using=router.db_for_write(NeuralModifier))
    protected_entries: list = []
    try:
        # Collector.collect assumes a homogeneous list — it keys off
        # the first instance's model. Call it per-model so every bucket
        # contributes its own forward walk to the same collector state.
        for bucket in per_model.values():
            collector.collect(bucket)
    except ProgrammingError:
        raise
    except Exception as exc:
        # Collector raises django.db.models.deletion.ProtectedError (and
        # RestrictedError) when a PROTECT/RESTRICT edge blocks the
        # delete. Harvest the blocking rows and surface them rather
        # than re-raise — the caller renders a full dialog, not a 500.
        blockers = getattr(exc, 'protected_objects', None) or getattr(
            exc, 'restricted_objects', None
        )
        if blockers is None:
            raise
        for obj in blockers:
            protected_entries.append(_row_entry(obj, reason='protected'))

    direct_entries: list = []
    cascade_entries: list = []
    for model, instances in collector.data.items():
        for obj in instances:
            entry = _row_entry(
                obj,
                reason=(
                    'direct' if (model, obj.pk) in direct_keys else 'cascade'
                ),
            )
            if (model, obj.pk) in direct_keys:
                direct_entries.append(entry)
            else:
                cascade_entries.append(entry)

    # fast_deletes hold QuerySets Collector intends to bulk-delete
    # without fetching instances — these are still real cascades that
    # need to show in the preview.
    for qs in collector.fast_deletes:
        for obj in qs:
            cascade_entries.append(_row_entry(obj, reason='cascade'))

    set_null_entries: list = []
    # Collector.field_updates shape is
    # ``{(field, value): [iterable_of_instances, ...]}``. Each list entry
    # is itself a QuerySet or instance list, so iterate twice.
    for (field, _value), buckets in collector.field_updates.items():
        for bucket in buckets:
            for obj in bucket:
                set_null_entries.append(
                    _row_entry(
                        obj,
                        reason='set_null:{0}'.format(field.name),
                    )
                )

    for bucket in (
        direct_entries,
        cascade_entries,
        set_null_entries,
        protected_entries,
    ):
        bucket.sort(key=lambda row: (row['model'], str(row['pk'])))

    return {
        'slug': slug,
        'row_count': len(direct_entries),
        'direct': direct_entries,
        'cascade': cascade_entries,
        'set_null': set_null_entries,
        'protected': protected_entries,
    }


def _row_entry(obj, *, reason: str) -> dict:
    """Serialize one row for the uninstall-preview payload."""
    model = type(obj)
    name = getattr(obj, 'name', None)
    label = str(name) if name else repr(obj)
    return {
        'app_label': model._meta.app_label,
        'model': '{0}.{1}'.format(
            model._meta.app_label, model._meta.model_name
        ),
        'pk': str(obj.pk),
        'name_or_repr': label,
        'reason': reason,
    }
