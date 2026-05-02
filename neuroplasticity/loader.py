"""NeuralModifier loader — genome / graft edition.

Pure-Python library called by the management commands and the AppConfig
boot hook. Manages the install / uninstall / create / save / save-as /
upgrade lifecycle plus the boot-time hash-check + side-effect re-import
pass.

Vocabulary:

* **genome** — the persisted identity (UUID + the
  ``neuroplasticity/genomes/<slug>.zip`` archive). The zip IS the
  genome; its UUID is declared in ``manifest['genome']`` and pinned as
  the ``NeuralModifier`` row's PK.
* **graft** — the runtime tree at ``neuroplasticity/grafts/<slug>/``
  where the genome's code, manifest, and media are extracted so the
  process can import them. Gitignored, derived state.
* **modifier** / **NeuralModifier** — the conceptual entity (database
  row + lifecycle status). The thing the user installs, uninstalls, and
  reasons about in the Modifier Garden.

Layout invariants:

    * ``neuroplasticity/genomes/<slug>.zip`` is the single source of
      truth. A modifier is AVAILABLE iff its zip exists and no DB row
      exists; INSTALLED once installed. The zip is committed.
    * ``neuroplasticity/grafts/<slug>/`` is the runtime install tree.
      Gitignored, derived state. Install copies into it; uninstall
      removes it (deferred to the next boot's orphan sweep on Windows).
    * ``neuroplasticity/operating_room/`` is the scratch space for
      transient install / upgrade / save / save-as extractions.
      Gitignored. Every operation creates a fresh ``tempfile.mkdtemp``
      (or a fresh file) under this root and removes it in a
      ``finally`` block.

State invariants:

    * AVAILABLE = zip on disk, no DB row. Uninstall deletes the
      ``NeuralModifier`` row entirely. CASCADE handles owned rows,
      logs, and events.
    * INCUBATOR is a special case: a permanently-grafted system-
      substrate genome that ships its own ``incubator.zip`` and
      auto-grafts on every Django boot via :func:`graft_incubator`. The
      INCUBATOR row is undeletable; uninstall against it cascade-clears
      its owned rows + media and re-grafts from the bootstrap zip
      (factory reset semantic).
    * CANONICAL is a different special case: DB-only, no manifest, no
      graft tree, no install path. Owns every fixture-shipped row.
    * INSTALLED_APPS is never mutated. Genomes contribute data, not
      apps.
    * Each DB object a genome creates carries a ``genome`` FK (from
      ``GenomeOwnedMixin``). Uninstall = ``NeuralModifier.delete()``
      and CASCADE removes everything pointing at it.
    * Hash drift between the on-disk manifest and
      ``NeuralModifier.manifest_hash`` flips status to BROKEN and the
      genome's entry modules are NOT imported.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import os
import shutil
import sys
import tempfile
import traceback
import uuid
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
    'genome',
    'author',
    'license',
    'entry_modules',
)


def grafts_root() -> Path:
    """Runtime install directory (gitignored). Created on first install."""
    return Path(settings.NEURAL_MODIFIER_GRAFTS_ROOT)


def genomes_root() -> Path:
    """On-disk collection of installable genome archives.

    Each ``*.zip`` under this directory is one genome the user can
    install through the Modifier Garden. The directory is committed to
    the repo — the zip IS the source of truth for its genome.
    """
    return Path(settings.NEURAL_MODIFIER_GENOMES_ROOT)


def operating_room_root() -> Path:
    """Transient scratch root for install / upgrade / save / save-as ops."""
    return Path(settings.NEURAL_MODIFIER_OPERATING_ROOM_ROOT)


def iter_genome_owned_models() -> Iterator[type]:
    """Every concrete model that carries the ``genome`` FK.

    These are the models a ``NeuralModifier`` can own rows in. Derived
    from ``GenomeOwnedMixin`` subclassing, so adding another is a
    single-line mixin edit plus a migration — no registry edit here.
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
    """Read manifest.json from inside a genome zip without extracting it."""
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


def _archive_manifest_hash(archive_path: Path) -> str:
    """Compute sha256 of the archive's manifest.json bytes.

    Read the same canonical bytes the install path will hash so the
    on-disk hash and the row's ``manifest_hash`` line up byte-for-byte.
    """
    with zipfile.ZipFile(archive_path) as zf:
        names = zf.namelist()
        top = sorted({n.split('/', 1)[0] for n in names if n.strip('/')})
        if len(top) != 1:
            raise ValueError(
                '[Neuroplasticity] Archive {0} must contain a single '
                'top-level directory; got {1}.'.format(archive_path, top)
            )
        manifest_name = '{0}/manifest.json'.format(top[0])
        return hashlib.sha256(zf.read(manifest_name)).hexdigest()


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


def create_empty_genome(
    slug: str,
    *,
    name: str = '',
    version: str = '0.1.0',
    author: str = '',
    license: str = '',
) -> NeuralModifier:
    """Scaffold a brand-new empty genome.

    Creates ``grafts/<slug>/`` with a manifest.json,
    ``modifier_data.json``, and ``code/`` dir, then registers a
    ``NeuralModifier`` row in INSTALLED state with no contributions.
    The user then stamps rows into it via the BEGIN_PLAY genome hook
    and packs the first archive via :func:`save_graft_to_genome`.

    Refuses if the slug is already in use as an installed modifier, the
    runtime dir already exists, the catalog already has
    ``genomes/<slug>.zip``, or the slug is reserved (``canonical`` /
    ``incubator``).
    """
    if slug == NeuralModifier.CANONICAL_SLUG:
        raise ValueError(
            '[Neuroplasticity] Cannot create a genome named {0!r}.'.format(
                NeuralModifier.CANONICAL_SLUG
            )
        )
    if slug == NeuralModifier.INCUBATOR_SLUG:
        raise ValueError(
            '[Neuroplasticity] Cannot create a genome named {0!r}; '
            'INCUBATOR is bootstrap-grafted from incubator.zip.'.format(
                NeuralModifier.INCUBATOR_SLUG
            )
        )
    if NeuralModifier.objects.filter(slug=slug).exists():
        raise FileExistsError(
            '[Neuroplasticity] Genome {0!r} is already installed.'.format(slug)
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
            '[Neuroplasticity] Graft dir already exists at {0}; '
            'uninstall first.'.format(runtime)
        )

    genome_uuid = uuid.uuid4()
    manifest = {
        'slug': slug,
        'name': name or slug,
        'version': version,
        'genome': str(genome_uuid),
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
        pk=genome_uuid,
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
        '[Neuroplasticity] Created empty genome %s (version %s).',
        slug,
        manifest['version'],
    )
    return modifier


def install_source_to_graft(source: Path, slug: str) -> NeuralModifier:
    """Copy ``source`` to the graft tree, import its code, load its data."""
    manifest_path = source / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    _validate_manifest(manifest)
    _check_requires(manifest)
    _guard_genome_uuid_collision(manifest, slug)
    manifest_hash = _compute_manifest_hash(manifest_path)

    runtime = grafts_root() / slug
    if runtime.exists():
        raise FileExistsError(
            '[Neuroplasticity] Graft dir exists at {0}; '
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


def uninstall_genome(slug: str) -> Optional[str]:
    """Three-mode uninstall, discriminated by slug.

    * ``CANONICAL`` — refused. Canonical is fixture-shipped, owns every
      core row, has no install path, and is undeletable.
    * ``INCUBATOR`` — cascade-clears every row owned by the incubator
      and wipes ``grafts/incubator/`` (including ``media/``), then
      re-grafts from ``incubator.zip``. The INCUBATOR row itself stays
      put. End state: a factory-fresh incubator. This IS the "Clear"
      semantic — uninstall+reinstall on INCUBATOR is the user's reset
      path; no separate clear endpoint.
    * Any other slug — delete owned rows in topological order, then the
      modifier row. CASCADE handles installation logs and events. Disk
      cleanup (``grafts/<slug>/``) is deferred to the next boot's
      orphan sweep so live file handles on Windows don't block the
      rmtree.

    Returns the deleted slug, or raises ``NeuralModifier.DoesNotExist``
    if there is no matching row.
    """
    modifier = NeuralModifier.objects.get(slug=slug)
    if modifier.pk == NeuralModifier.CANONICAL:
        raise ValueError(
            '[Neuroplasticity] Cannot uninstall the canonical modifier.'
        )
    if modifier.pk == NeuralModifier.INCUBATOR:
        return _reset_incubator(modifier)

    runtime = grafts_root() / slug
    _remove_code_from_path(runtime)

    with transaction.atomic():
        for model in _owned_delete_order():
            model.objects.filter(genome=modifier).delete()
        modifier.delete()
    logger.info('[Neuroplasticity] Uninstalled %s.', slug)
    return slug


def _reset_incubator(modifier: NeuralModifier) -> str:
    """Cascade-clear the incubator's owned rows + media, then re-graft.

    The INCUBATOR row stays put; everything ELSE inside it is wiped and
    rebuilt from ``incubator.zip``. Used by :func:`uninstall_genome` as
    the "factory reset" path for the default workspace.
    """
    runtime = grafts_root() / NeuralModifier.INCUBATOR_SLUG
    _remove_code_from_path(runtime)

    with transaction.atomic():
        for model in _owned_delete_order():
            model.objects.filter(genome=modifier).delete()
        # Reset the row's manifest cache so graft_incubator restamps it
        # from the freshly-extracted zip.
        modifier.manifest_hash = ''
        modifier.manifest_json = {}
        modifier.save(update_fields=['manifest_hash', 'manifest_json'])

    if runtime.exists():
        # Best-effort wipe — graft_incubator will re-extract regardless.
        # On Windows this may leave .pyc handles behind; the boot orphan
        # sweep would catch the remnant in a fresh process, but
        # graft_incubator's _merge_extracted_into_graft is also
        # designed to stomp existing entries.
        try:
            shutil.rmtree(runtime)
        except Exception:
            logger.warning(
                '[Neuroplasticity] Could not rmtree %s during '
                'incubator reset; graft_incubator will overwrite.',
                runtime,
            )

    graft_incubator()
    logger.info(
        '[Neuroplasticity] Reset INCUBATOR — graft cleared and re-baked '
        'from incubator.zip.',
    )
    return NeuralModifier.INCUBATOR_SLUG


def graft_incubator() -> None:
    """Bootstrap the INCUBATOR genome on every Django boot.

    INCUBATOR is a permanently-grafted system-substrate genome — has a
    manifest, has a graft tree, has a real ``urls.py``, ships
    ``neuroplasticity/genomes/incubator.zip`` exactly like every other
    genome. The only thing that distinguishes it from a user-installed
    bundle is that this function runs from the AppConfig boot path to
    keep it grafted and INSTALLED at all times.

    Idempotent. Operations:

    1. If the bootstrap zip is missing, log a warning and skip — the
       INCUBATOR row stays as fixture-shipped (manifest_hash='').
    2. If ``grafts/incubator/manifest.json`` is missing or its sha256
       differs from the archive's manifest hash, re-extract from
       ``incubator.zip`` (preserving any user-uploaded ``media/``
       contents).
    3. Update the INCUBATOR row (``manifest_hash``, ``manifest_json``,
       ``status_id=INSTALLED``) to match what's now on disk.
    4. Ensure the graft's ``code/`` dir is on ``sys.path`` so URL
       discovery and entry-module imports can find it.

    No restart, no user-facing acetylcholine. The boot wrapper in
    ``neuroplasticity/boot.py`` swallows exceptions so a graft hiccup
    never takes down the first request.
    """
    archive_path = genomes_root() / 'incubator.zip'
    if not archive_path.exists():
        logger.warning(
            '[Neuroplasticity] incubator.zip not found at %s; '
            'INCUBATOR graft skipped.',
            archive_path,
        )
        return

    manifest = read_archive_manifest(archive_path)
    if manifest.get('slug') != NeuralModifier.INCUBATOR_SLUG:
        logger.error(
            '[Neuroplasticity] %s manifest declares slug %r — '
            'expected %r. Refusing to graft.',
            archive_path,
            manifest.get('slug'),
            NeuralModifier.INCUBATOR_SLUG,
        )
        return
    try:
        manifest_genome = uuid.UUID(str(manifest.get('genome', '')))
    except (ValueError, TypeError):
        manifest_genome = None
    if manifest_genome != NeuralModifier.INCUBATOR:
        logger.error(
            '[Neuroplasticity] %s manifest genome UUID %r does not '
            'match NeuralModifier.INCUBATOR. Refusing to graft.',
            archive_path,
            manifest.get('genome'),
        )
        return

    runtime = grafts_root() / NeuralModifier.INCUBATOR_SLUG
    runtime_manifest = runtime / 'manifest.json'

    archive_hash = _archive_manifest_hash(archive_path)
    needs_extract = True
    if runtime_manifest.exists():
        runtime_hash = _compute_manifest_hash(runtime_manifest)
        if runtime_hash == archive_hash:
            needs_extract = False

    if needs_extract:
        operating_room_root().mkdir(parents=True, exist_ok=True)
        extraction = Path(tempfile.mkdtemp(dir=str(operating_room_root())))
        try:
            extracted = _extract_archive_into(
                archive_path, extraction, NeuralModifier.INCUBATOR_SLUG,
            )
            _merge_extracted_into_graft(extracted, runtime)
        finally:
            if extraction.exists():
                shutil.rmtree(extraction, ignore_errors=True)

    # Re-read the post-merge manifest hash; should match the archive
    # exactly, and it's what the boot pass compares against.
    final_hash = _compute_manifest_hash(runtime_manifest)

    incubator = NeuralModifier.objects.filter(
        pk=NeuralModifier.INCUBATOR,
    ).first()
    if incubator is None:
        # The fixture is the source of truth for the row; if it isn't
        # loaded yet (fresh DB before fixtures land), there's nothing
        # to update. The next boot will see the row.
        logger.debug(
            '[Neuroplasticity] INCUBATOR row not present; '
            'graft on disk only.',
        )
        return

    needs_save = False
    if incubator.manifest_hash != final_hash:
        incubator.manifest_hash = final_hash
        needs_save = True
    if incubator.manifest_json != manifest:
        incubator.manifest_json = manifest
        needs_save = True
    if incubator.status_id != NeuralModifierStatus.INSTALLED:
        incubator.status_id = NeuralModifierStatus.INSTALLED
        needs_save = True
    if (incubator.version or '0.0.0') != manifest.get('version', '0.0.0'):
        incubator.version = manifest.get('version', '0.0.0')
        needs_save = True
    if needs_save:
        incubator.save(
            update_fields=[
                'manifest_hash',
                'manifest_json',
                'status',
                'version',
            ],
        )

    _ensure_code_on_path(runtime)


def _merge_extracted_into_graft(extracted: Path, target: Path) -> None:
    """Copy extracted archive contents into ``target``, replacing every
    top-level entry except ``media/``.

    ``media/`` is preserved intentionally — user-uploaded Avatar bytes
    live there and must survive a re-graft. Files inside the extracted
    ``media/`` (e.g. the bundled ``.gitkeep`` placeholder) are copied
    only if they don't already exist on disk.
    """
    target.mkdir(parents=True, exist_ok=True)
    for child in extracted.iterdir():
        target_child = target / child.name
        if child.name == 'media':
            target_child.mkdir(parents=True, exist_ok=True)
            for path in child.rglob('*'):
                if path.is_dir():
                    continue
                rel = path.relative_to(child)
                dest = target_child / rel
                if dest.exists():
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(path), str(dest))
            continue
        if target_child.exists():
            if target_child.is_dir():
                shutil.rmtree(target_child)
            else:
                target_child.unlink()
        if child.is_dir():
            shutil.copytree(str(child), str(target_child))
        else:
            shutil.copy2(str(child), str(target_child))


def upgrade_source_to_graft(
    source: Path, slug: str, *, allow_same_version: bool = False
) -> dict:
    """Diff new modifier_data.json against currently-owned rows; apply the delta.

    Returns::

        {previous_version, new_version, created, updated, deleted}

    Raises:
        NeuralModifier.DoesNotExist: no genome with that slug.
        FileNotFoundError: source missing on disk.
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
            '[Neuroplasticity] No genome source at {0}.'.format(source)
        )

    manifest_path = source / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    _validate_manifest(manifest)
    _check_requires(manifest)
    _guard_genome_uuid_collision(manifest, slug)
    manifest_genome = uuid.UUID(manifest['genome'])
    if manifest_genome != modifier.pk:
        raise ValueError(
            '[Neuroplasticity] Manifest genome {0} does not match the '
            'installed genome {1!r} (pk {2}); refusing upgrade.'.format(
                manifest_genome, slug, modifier.pk
            )
        )

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


def upgrade_genome(slug: str, *, allow_same_version: bool = False) -> dict:
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
        return upgrade_source_to_graft(
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
    return '0.0.1'


def save_graft_to_genome(slug: str) -> dict:
    """Serialize every owned row + graft tree back into ``genomes/<slug>.zip``.

    Direction: graft (live runtime tree + DB rows) → genome (zip on
    disk). Atomically replaces the on-disk archive. Includes manifest,
    modifier_data.json (every ``GenomeOwnedMixin`` row filtered by
    ``genome=modifier``), the graft's ``code/`` tree, and any user-
    uploaded files under ``media/``. SpikeTrains / Spikes /
    ReasoningSessions are intentionally excluded — runtime telemetry,
    not bundle content.

    Always bumps the semver patch on save: the manifest's ``version``
    field is incremented, the new value is mirrored onto the
    ``NeuralModifier.version`` row, and the bumped manifest is what
    lands in the zip.

    Returns::

        {'slug', 'bytes_written', 'row_count', 'zip_path',
         'previous_version', 'new_version', 'backup_path'}
    """
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

    runtime_graft = grafts_root() / slug
    manifest_path = runtime_graft / 'manifest.json'
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

    code_dir = runtime_graft / 'code'
    media_dir = runtime_graft / 'media'

    # Pre-flight (FIRST — before any state mutation): refuse the save
    # if the manifest declares entry_modules but the graft's code tree
    # doesn't carry them. Catches the silent-broken-zip path that
    # earlier overwrote a working unreal.zip with a code-less archive.
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

            # Genome-owned media (e.g. Avatar display=FILE bytes) — bake
            # whatever is under grafts/<slug>/media/ into the archive at
            # <slug>/media/. Round-trips on install via the existing
            # extracted-source copytree into the new graft tree.
            if media_dir.exists():
                for path in sorted(media_dir.rglob('*')):
                    if path.is_dir():
                        continue
                    arcname = (
                        Path(slug) / 'media' / path.relative_to(media_dir)
                    )
                    zf.write(path, arcname.as_posix())

        _verify_staged_archive(staging_path, slug, declared_modules)

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
        '[Neuroplasticity] Saved %s graft to genome (%d rows, %d bytes, '
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


def save_as_genome(
    source_slug: str, new_slug: str, *, new_name: str = '',
) -> NeuralModifier:
    """Forge a new genome from another modifier's owned rows + media.

    Source can be ANY visible modifier (INCUBATOR included; CANONICAL
    refused). Owned rows are deep-cloned with fresh PKs so the source
    keeps its rows intact, FKs between cloned rows are remapped onto
    the new PKs, FKs that point at non-source rows (e.g. CANONICAL
    vocabulary) keep their values. ``code/`` and ``media/`` are
    copytree'd from the source graft. The new genome's zip is baked
    via :func:`save_graft_to_genome`-equivalent serialize-into-zip,
    then installed live via :func:`install_genome_to_graft`.

    Refusals (all 400-friendly):
        * blank or reserved new_slug (canonical / incubator)
        * new_slug already in the catalog or already installed
        * source is canonical
        * source modifier missing
    """
    new_slug = (new_slug or '').strip()
    if not new_slug:
        raise ValueError('[Neuroplasticity] save-as: new slug is required.')
    if new_slug == NeuralModifier.CANONICAL_SLUG:
        raise ValueError(
            '[Neuroplasticity] save-as: cannot use reserved slug {0!r}.'.format(
                NeuralModifier.CANONICAL_SLUG,
            )
        )
    if new_slug == NeuralModifier.INCUBATOR_SLUG:
        raise ValueError(
            '[Neuroplasticity] save-as: cannot use reserved slug {0!r}.'.format(
                NeuralModifier.INCUBATOR_SLUG,
            )
        )
    if NeuralModifier.objects.filter(slug=new_slug).exists():
        raise FileExistsError(
            '[Neuroplasticity] save-as: a genome named {0!r} is already '
            'installed.'.format(new_slug)
        )
    if (genomes_root() / '{0}.zip'.format(new_slug)).exists():
        raise FileExistsError(
            '[Neuroplasticity] save-as: catalog already has '
            '{0}.zip.'.format(new_slug)
        )

    source = NeuralModifier.objects.get(slug=source_slug)
    if source.pk == NeuralModifier.CANONICAL:
        raise ValueError(
            '[Neuroplasticity] save-as: cannot save-as from the canonical '
            'modifier.'
        )

    new_genome_uuid = uuid.uuid4()
    source_manifest = dict(source.manifest_json or {})
    new_manifest = {
        'slug': new_slug,
        'name': new_name.strip() or new_slug,
        'version': '0.0.0',
        'genome': str(new_genome_uuid),
        'author': source_manifest.get('author', ''),
        'license': source_manifest.get('license', ''),
        'description': source_manifest.get(
            'description', 'Forged from {0!r}.'.format(source_slug),
        ),
        # Don't carry source's entry_modules forward — the new genome's
        # code/ tree is copied from the source graft, so any imports the
        # source declared still resolve, but the new genome starts with
        # an empty contract until the user explicitly opts in.
        'entry_modules': [],
        'requires_are_self': source_manifest.get(
            'requires_are_self', '>=0.1.0',
        ),
    }

    op_root = operating_room_root()
    op_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=str(op_root), prefix='saveas-'))
    new_bundle = staging / new_slug
    new_bundle.mkdir(parents=True)
    try:
        (new_bundle / 'manifest.json').write_text(
            json.dumps(new_manifest, indent=2) + '\n',
        )

        source_graft = grafts_root() / source_slug
        source_code = source_graft / 'code'
        if source_code.exists():
            shutil.copytree(str(source_code), str(new_bundle / 'code'))
        else:
            (new_bundle / 'code').mkdir(parents=True, exist_ok=True)

        source_media = source_graft / 'media'
        target_media = new_bundle / 'media'
        if source_media.exists():
            shutil.copytree(str(source_media), str(target_media))
        else:
            target_media.mkdir(parents=True, exist_ok=True)

        modifier_data = _build_remapped_owned_data(source, new_genome_uuid)
        (new_bundle / 'modifier_data.json').write_text(
            json.dumps(modifier_data, indent=2) + '\n',
        )

        # Bake the new zip atomically, then install it through the
        # standard archive path so the row + log + event trail look
        # identical to a hand-installed genome.
        archive_path = genomes_root() / '{0}.zip'.format(new_slug)
        staging_zip_fd, staging_zip_name = tempfile.mkstemp(
            prefix='{0}-saveas-'.format(new_slug),
            suffix='.zip',
            dir=str(op_root),
        )
        os.close(staging_zip_fd)
        staging_zip = Path(staging_zip_name)
        try:
            with zipfile.ZipFile(staging_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                for path in sorted(new_bundle.rglob('*')):
                    if path.is_dir():
                        continue
                    arcname = (
                        Path(new_slug) / path.relative_to(new_bundle)
                    )
                    zf.write(path, arcname.as_posix())
            os.replace(str(staging_zip), str(archive_path))
        except Exception:
            if staging_zip.exists():
                staging_zip.unlink()
            raise

        new_modifier = install_genome_to_graft(archive_path)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    logger.info(
        '[Neuroplasticity] save-as %s -> %s (%d cloned rows).',
        source_slug,
        new_slug,
        len(modifier_data),
    )
    return new_modifier


def _build_remapped_owned_data(
    source: NeuralModifier, new_genome_uuid: uuid.UUID,
) -> list:
    """Serialize every row owned by ``source`` with fresh PKs and remap
    cross-row FKs onto the new PK space.

    First pass collects (model_label, old_pk) and assigns a fresh
    ``uuid.uuid4()`` for each. Second pass serializes via Django's JSON
    serializer, walks every FK / M2M field, and rewrites references
    that fall inside the same source-owned set onto their new PK.
    References that fall outside (CANONICAL vocabulary, etc.) keep
    their original values. The genome FK is stripped — the install
    side stamps it.

    Unique non-PK fields (e.g. ``NameMixin.name``) get an
    8-char-hex suffix derived from ``new_genome_uuid`` to avoid
    install-time collisions against the source rows that still exist.
    The suffix is deterministic per save-as call, so re-running save-as
    against the same source produces a different suffix every time.
    """
    suffix = '-{0}'.format(str(new_genome_uuid).split('-')[0])

    pk_map: dict = {}  # (model_label, old_pk_str) -> new_pk_str
    source_pks_by_label: dict = {}  # model_label -> set of old_pk strings

    for model in iter_genome_owned_models():
        old_pks = list(
            model.objects.filter(genome=source).values_list('pk', flat=True)
        )
        if not old_pks:
            continue
        label = '{0}.{1}'.format(
            model._meta.app_label, model._meta.model_name,
        )
        source_pks_by_label[label] = {str(pk) for pk in old_pks}
        for pk in old_pks:
            pk_map[(label, str(pk))] = str(uuid.uuid4())

    if not pk_map:
        return []

    payload: list = []
    for model in iter_genome_owned_models():
        qs = model.objects.filter(genome=source).order_by('pk')
        if not qs.exists():
            continue
        label = '{0}.{1}'.format(
            model._meta.app_label, model._meta.model_name,
        )
        unique_string_fields = [
            f for f in model._meta.fields
            if f.unique
            and not f.primary_key
            and not f.is_relation
            and f.get_internal_type() in {'CharField', 'TextField', 'SlugField'}
        ]

        rows = json.loads(serializers.serialize('json', qs))
        for row in rows:
            old_pk = str(row['pk'])
            row['pk'] = pk_map[(label, old_pk)]
            row.get('fields', {}).pop('genome', None)

            # Unique field disambiguation — append the new-genome suffix
            # to whatever's there. Truncate to the field's max_length
            # so the post-suffix value still fits. Only applies to
            # string-shaped unique fields; numeric / bool / date unique
            # fields are out-of-scope and would already be unusual on a
            # genome-owned model.
            for field in unique_string_fields:
                value = row['fields'].get(field.name)
                if not isinstance(value, str) or not value:
                    continue
                max_length = getattr(field, 'max_length', None) or 255
                # Reserve room for the suffix.
                budget = max(1, max_length - len(suffix))
                row['fields'][field.name] = (
                    value[:budget] + suffix
                )

            for field in model._meta.fields:
                if not field.is_relation or field.many_to_many:
                    continue
                if field.name == 'genome':
                    continue
                related = field.related_model
                related_label = '{0}.{1}'.format(
                    related._meta.app_label, related._meta.model_name,
                )
                if related_label not in source_pks_by_label:
                    continue
                value = row['fields'].get(field.name)
                if value is None:
                    continue
                sv = str(value)
                if sv in source_pks_by_label[related_label]:
                    row['fields'][field.name] = pk_map[(related_label, sv)]

            for field in model._meta.many_to_many:
                related = field.related_model
                related_label = '{0}.{1}'.format(
                    related._meta.app_label, related._meta.model_name,
                )
                if related_label not in source_pks_by_label:
                    continue
                values = row['fields'].get(field.name) or []
                new_values: list = []
                for v in values:
                    sv = str(v)
                    if sv in source_pks_by_label[related_label]:
                        new_values.append(pk_map[(related_label, sv)])
                    else:
                        new_values.append(sv)
                row['fields'][field.name] = new_values

            payload.append(row)

    return payload


def _missing_entry_modules(code_dir: Path, entry_modules: list) -> list:
    """Return the subset of ``entry_modules`` not findable under
    ``code_dir`` as either ``<name>/__init__.py`` or ``<name>.py``.
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


def iter_installed_genomes() -> Iterable[NeuralModifier]:
    """Yield every NeuralModifier whose status is INSTALLED, except CANONICAL.

    CANONICAL is fixture-shipped with no manifest and no graft, so it
    can never participate in the boot pass / URL discovery / catalog
    flows that consume this iterator. Filtering it out at the source
    keeps every consumer from re-deriving the exclusion. INCUBATOR IS
    yielded — it's a real grafted genome bootstrapped via
    :func:`graft_incubator`.
    """
    return NeuralModifier.objects.filter(
        status_id=NeuralModifierStatus.INSTALLED,
    ).exclude(pk=NeuralModifier.CANONICAL)


def boot_genomes() -> None:
    """AppConfig-hook driven re-import pass; flips BROKEN on drift.

    Order:
        1. ``graft_incubator()`` — guarantee INCUBATOR is on disk and
           healthy in the DB before any orphan sweep or per-row check.
        2. Orphan sweep — remove graft dirs whose slug has no DB row.
        3. Per-genome boot — read manifest, compare hash, import entry
           modules; flip BROKEN on any failure.
        4. Mutex sanity — guarantee exactly-one ``selected`` /
           ``selected_for_edit`` rows.
    """
    try:
        graft_incubator()
    except Exception:
        logger.exception(
            '[Neuroplasticity] graft_incubator failed during boot.',
        )

    runtime = grafts_root()
    if not runtime.exists():
        _ensure_selection_mutexes()
        return

    try:
        bootable = list(iter_installed_genomes())
    except (OperationalError, ProgrammingError):
        logger.debug(
            '[Neuroplasticity] boot_genomes skipped — table not ready.'
        )
        return

    by_slug = {m.slug: m for m in bootable}

    # Orphan sweep: remove any runtime dir that no longer has a DB
    # row. Uninstall defers disk cleanup to here so it runs in a
    # fresh process with empty sys.modules — Windows file locks from
    # the prior process are gone. Real rmtree, loud on failure.
    for graft_dir in sorted(runtime.iterdir()):
        if not graft_dir.is_dir() or graft_dir.name in by_slug:
            continue
        try:
            shutil.rmtree(graft_dir)
        except Exception:
            logger.exception(
                '[Neuroplasticity] Orphan sweep failed for %s',
                graft_dir,
            )

    for graft_dir in sorted(runtime.iterdir()):
        if not graft_dir.is_dir():
            continue
        modifier = by_slug.get(graft_dir.name)
        if modifier is None:
            continue
        _boot_one(graft_dir, modifier)

    _ensure_selection_mutexes()


def _ensure_selection_mutexes() -> None:
    """Guarantee exactly one ``ProjectEnvironment.selected`` and exactly
    one ``NeuralModifier.selected_for_edit`` after every boot.

    Per-write ``save()`` overrides on each model already enforce the
    "only one true at a time" invariant, but a duplicate fixture load
    (re-running the installer with a genome already installed) can slip
    rows past those overrides via raw inserts. This sanity check is
    cheap and idempotent: count the trues, and if the count isn't 1,
    snap the canonical fallback to selected and clear everyone else.

    Fallbacks:
        * ``ProjectEnvironment`` → ``DEFAULT_ENVIRONMENT``
          (zygote-shipped, ``genome=CANONICAL``).
        * ``NeuralModifier`` → ``INCUBATOR``.
    """
    try:
        from environments.models import ProjectEnvironment
    except (OperationalError, ProgrammingError, ImportError):
        return

    try:
        env_selected = ProjectEnvironment.objects.filter(
            selected=True,
        ).count()
        if env_selected != 1:
            default_env_pk = ProjectEnvironment.DEFAULT_ENVIRONMENT
            with transaction.atomic():
                ProjectEnvironment.objects.filter(
                    selected=True,
                ).update(selected=False)
                ProjectEnvironment.objects.filter(
                    pk=default_env_pk,
                ).update(selected=True)
            logger.info(
                '[Neuroplasticity] selection mutex reset: '
                'ProjectEnvironment.selected snapped to default (had %d).',
                env_selected,
            )
    except (OperationalError, ProgrammingError):
        pass

    try:
        edit_selected = NeuralModifier.objects.filter(
            selected_for_edit=True,
        ).count()
        if edit_selected != 1:
            with transaction.atomic():
                NeuralModifier.objects.filter(
                    selected_for_edit=True,
                ).update(selected_for_edit=False)
                NeuralModifier.objects.filter(
                    pk=NeuralModifier.INCUBATOR,
                ).update(selected_for_edit=True)
            logger.info(
                '[Neuroplasticity] selection mutex reset: '
                'NeuralModifier.selected_for_edit snapped to INCUBATOR '
                '(had %d).',
                edit_selected,
            )
    except (OperationalError, ProgrammingError):
        pass


def _boot_one(graft_dir: Path, modifier: NeuralModifier) -> None:
    manifest_path = graft_dir / 'manifest.json'
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
    _ensure_code_on_path(graft_dir)
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
    """Reuse an existing row by slug, otherwise create one with the
    manifest-pinned UUID as PK.

    Genomes declare a stable UUID in their manifest; install uses it as
    the row's PK so identity is portable across machines and survives
    uninstall/reinstall cycles. Slug-collision short-circuit keeps
    reinstall/upgrade pointing at the same row.
    """
    modifier = NeuralModifier.objects.filter(slug=slug).first()
    if modifier is not None:
        return modifier
    return NeuralModifier.objects.create(
        pk=uuid.UUID(manifest['genome']),
        slug=slug,
        name=manifest.get('name', slug),
        version=manifest.get('version', ''),
        author=manifest.get('author', ''),
        license=manifest.get('license', ''),
        manifest_hash=manifest_hash,
        manifest_json=manifest,
        status_id=NeuralModifierStatus.INSTALLED,
    )


def _guard_genome_uuid_collision(manifest: dict, slug: str) -> None:
    """Refuse the install if the manifest's genome UUID is already in use
    by a different slug. Same UUID + same slug is the upgrade/reinstall
    path and is allowed through.
    """
    manifest_genome = uuid.UUID(manifest['genome'])
    existing_slug = (
        NeuralModifier.objects.filter(pk=manifest_genome)
        .exclude(slug=slug)
        .values_list('slug', flat=True)
        .first()
    )
    if existing_slug is not None:
        raise ValueError(
            '[Neuroplasticity] Manifest genome {0} is already used by '
            'installed genome {1!r}; refusing to install {2!r} onto the '
            'same UUID.'.format(manifest_genome, existing_slug, slug)
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
    genome_value = manifest['genome']
    if not isinstance(genome_value, str):
        raise ValueError(
            '[Neuroplasticity] Manifest genome must be a UUID string; got '
            '{0!r}.'.format(type(genome_value).__name__)
        )
    try:
        uuid.UUID(genome_value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(
            '[Neuroplasticity] Manifest genome {0!r} is not a valid UUID: '
            '{1}'.format(genome_value, exc)
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


def _ensure_code_on_path(graft_dir: Path) -> None:
    code_dir = str((graft_dir / 'code').resolve())
    if code_dir not in sys.path:
        sys.path.insert(0, code_dir)


def _remove_code_from_path(graft_dir: Path) -> None:
    code_dir = str((graft_dir / 'code').resolve())
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
    already exists and is owned by canonical, another genome, or the
    incubator, the install is refused with a clear error. Same-slug
    reinstalls are allowed through because the existing row's genome
    already points at this modifier.
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
    """Raise if ``target.pk`` is already owned by anyone but this modifier.

    Called per-row inside the install / upgrade deserialize loop.
    The existing row's ``genome_id`` decides the verdict:

    * matches the installing modifier — OK (same-slug reinstall /
      upgrade's own-row update).
    * equals ``NeuralModifier.CANONICAL`` — refuse. Genomes must not
      overwrite core-shipped rows.
    * equals ``NeuralModifier.INCUBATOR`` — refuse. Genomes must not
      overwrite rows the user created in the default workspace.
    * points at any other ``NeuralModifier`` — refuse. Genomes must
      not overwrite rows another genome already owns.
    """
    model = type(target)
    existing_genome_id = (
        model.objects.filter(pk=target.pk)
        .values_list('genome_id', flat=True)
        .first()
    )
    if existing_genome_id is None:
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
        owner_label = (
            repr(existing_slug) if existing_slug else 'unknown-genome'
        )

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


def install_genome_to_graft(archive_path: Path) -> NeuralModifier:
    """Install a genome from a zip on disk.

    Direction: genome (zip) → graft (live runtime tree). Extracts the
    archive into operating_room/scratch, then hands off to
    :func:`install_source_to_graft`.
    """
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
        return install_source_to_graft(source, slug)
    finally:
        if extraction.exists():
            shutil.rmtree(extraction, ignore_errors=True)


def genome_uninstall_preview(slug: str) -> dict:
    """Full cascade tree for an uninstall, built via ``Collector.collect()``.

    Gathers every row the genome directly owns (``genome=modifier``
    across the GenomeOwnedMixin consumers), feeds them into a
    ``django.db.models.deletion.Collector`` — the same collector Django
    admin uses for its delete-confirmation page — and returns the
    walked tree as::

        {
          'slug': str,
          'row_count': int,
          'direct':    [{...}, ...],  # rows the genome owns
          'cascade':   [{...}, ...],  # rows CASCADE removes with them
          'set_null':  [{...}, ...],  # rows whose FK gets nulled
          'protected': [{...}, ...],  # rows that would PROTECT-block
        }

    Each entry is ``{app_label, model, pk, name_or_repr, reason}``. The
    UI renders the full tree in the confirmation dialog.
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
        for bucket in per_model.values():
            collector.collect(bucket)
    except ProgrammingError:
        raise
    except Exception as exc:
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

    for qs in collector.fast_deletes:
        for obj in qs:
            cascade_entries.append(_row_entry(obj, reason='cascade'))

    set_null_entries: list = []
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
