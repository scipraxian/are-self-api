"""Lifecycle tests for the NeuralModifier loader and management commands.

Covers install / uninstall happy paths plus the two BROKEN failure
modes (manifest hash drift, entry-module import failure). Tests build
self-contained fake bundles in a tmp directory and override the three
root settings, so the committed Unreal bundle is never touched.

Under the genome-FK scheme there is no side-car contribution table —
each installed row carries a ``genome`` FK back to the owning
``NeuralModifier``. Uninstall is just ``modifier.delete()``; CASCADE
does the rest.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import textwrap
import uuid
from pathlib import Path
from typing import Iterable, Optional

from django.test import TestCase, override_settings

import zipfile

from hypothalamus.models import AIModelTags
from identity.models import (
    Avatar,
    AvatarSelectedDisplayType,
    IdentityAddon,
)
from neuroplasticity import loader
from neuroplasticity.models import (
    NeuralModifier,
    NeuralModifierInstallationEvent,
    NeuralModifierInstallationEventType,
    NeuralModifierInstallationLog,
    NeuralModifierStatus,
)


def _make_addon_payload(name: str) -> dict:
    """Serialized IdentityAddon row — UUID PK, GenomeOwnedMixin target."""
    return {
        'model': 'identity.identityaddon',
        'pk': str(uuid.uuid4()),
        'fields': {
            'name': name,
            'description': 'fake bundle addon',
            'addon_class_name': None,
            'function_slug': None,
            'phase': None,
        },
    }


def _make_tag_payload(name: str) -> dict:
    """Serialized AIModelTags row — UUID PK, no genome FK.

    Kept in a couple of legacy tests that still exercise non-owned
    deserialization (pure UUID vocabulary rows).
    """
    return {
        'model': 'hypothalamus.aimodeltags',
        'pk': str(uuid.uuid4()),
        'fields': {'name': name, 'description': 'fake bundle row'},
    }


def build_fake_bundle_archive(
    genomes_root: Path,
    slug: str,
    *,
    modifier_data: Optional[list] = None,
    entry_modules: Iterable[str] = ('are_self_fake_catalog',),
) -> Path:
    """Build a synthetic bundle in a tmp dir and zip it into the genomes dir."""
    import zipfile

    genomes_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        scratch = Path(td) / 'scratch'
        scratch.mkdir()
        bundle_dir = build_fake_bundle(
            scratch,
            slug,
            modifier_data=modifier_data,
            entry_modules=entry_modules,
        )
        archive_path = genomes_root / '{0}.zip'.format(slug)
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(bundle_dir.rglob('*')):
                if path.is_dir():
                    continue
                arcname = Path(slug) / path.relative_to(bundle_dir)
                zf.write(path, arcname.as_posix())
    return archive_path


def build_fake_bundle(
    scratch_root: Path,
    slug: str,
    *,
    modifier_data: Optional[list] = None,
    entry_modules: Iterable[str] = ('are_self_fake',),
    with_broken_import: bool = False,
    namespace_pkg: Optional[str] = None,
) -> Path:
    """Write a minimal valid-shape bundle into scratch_root/<slug>/.

    Default payload is three IdentityAddon rows — those carry
    GenomeOwnedMixin, so they exercise the genome-stamping loader path.
    """
    if modifier_data is None:
        modifier_data = [
            _make_addon_payload('{0}-alpha-{1}'.format(slug, uuid.uuid4().hex[:8])),
            _make_addon_payload('{0}-beta-{1}'.format(slug, uuid.uuid4().hex[:8])),
            _make_addon_payload('{0}-gamma-{1}'.format(slug, uuid.uuid4().hex[:8])),
        ]
    pkg_name = namespace_pkg or list(entry_modules)[0]
    bundle = scratch_root / slug
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / 'manifest.json').write_text(
        json.dumps(
            {
                'slug': slug,
                'name': 'Fake {0}'.format(slug),
                'version': '0.0.1',
                'genome': str(uuid.uuid4()),
                'author': 'tests',
                'license': 'MIT',
                'description': 'Test bundle.',
                'entry_modules': list(entry_modules),
                'requires_are_self': '>=0.0.0',
            },
            indent=2,
        )
        + '\n'
    )
    (bundle / 'modifier_data.json').write_text(
        json.dumps(modifier_data, indent=2) + '\n'
    )
    (bundle / 'code').mkdir(exist_ok=True)
    (bundle / 'code' / '__init__.py').write_text('')
    pkg_dir = bundle / 'code' / pkg_name
    pkg_dir.mkdir(exist_ok=True)
    if with_broken_import:
        body = textwrap.dedent(
            '''
            """Test fixture: deliberately raises at import time."""
            raise ImportError('test-injected import failure')
            '''
        ).lstrip()
    else:
        body = '"""Test fixture: imports cleanly."""\n'
    (pkg_dir / '__init__.py').write_text(body)
    return bundle


class ModifierLifecycleTestCase(TestCase):
    """Base class — wires tmp roots, loads neuroplasticity reference data."""

    fixtures = ['neuroplasticity/fixtures/genetic_immutables.json']

    def setUp(self):
        super().setUp()
        self._tmp_root = Path(tempfile.mkdtemp(prefix='neuroplasticity-test-'))
        self.scratch_root = self._tmp_root / 'scratch'
        self.genomes_root = self._tmp_root / 'genomes'
        self.grafts_root = self._tmp_root / 'grafts'
        self.operating_room_root = self._tmp_root / 'operating_room'
        self.scratch_root.mkdir()
        self.genomes_root.mkdir()
        self.grafts_root.mkdir()
        self.operating_room_root.mkdir()
        self._sys_path_snapshot = list(sys.path)
        self._sys_modules_snapshot = set(sys.modules.keys())
        self._settings_override = override_settings(
            NEURAL_MODIFIER_GENOMES_ROOT=str(self.genomes_root),
            NEURAL_MODIFIER_GRAFTS_ROOT=str(self.grafts_root),
            NEURAL_MODIFIER_OPERATING_ROOM_ROOT=str(self.operating_room_root),
        )
        self._settings_override.enable()

    def tearDown(self):
        self._settings_override.disable()
        sys.path[:] = self._sys_path_snapshot
        for name in list(sys.modules.keys()):
            if name not in self._sys_modules_snapshot:
                sys.modules.pop(name, None)
        shutil.rmtree(self._tmp_root, ignore_errors=True)
        super().tearDown()

    def install_fake(self, slug: str) -> NeuralModifier:
        return loader.install_source_to_graft(
            self.scratch_root / slug, slug
        )

    def _owned_addon_count(self, modifier) -> int:
        return IdentityAddon.objects.filter(genome=modifier).count()


class InstallHappyPathTest(ModifierLifecycleTestCase):
    def test_install_happy_path(self):
        """Assert install stamps genome_id on every GenomeOwnedMixin row."""
        build_fake_bundle(self.scratch_root, 'alpha')

        modifier = self.install_fake('alpha')

        self.assertEqual(modifier.status_id, NeuralModifierStatus.INSTALLED)
        self.assertEqual(self._owned_addon_count(modifier), 3)
        self.assertEqual(
            IdentityAddon.objects.filter(
                name__startswith='alpha-'
            ).count(),
            3,
        )
        self.assertEqual(modifier.name, 'Fake alpha')
        self.assertTrue((self.grafts_root / 'alpha').is_dir())
        self.assertIn('are_self_fake', sys.modules)
        log = modifier.current_installation()
        self.assertIsNotNone(log)
        events = list(log.events.all())
        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0].event_type_id,
            NeuralModifierInstallationEventType.INSTALL,
        )
        self.assertEqual(events[0].event_data['rows'], 3)


class UninstallFullRollbackTest(ModifierLifecycleTestCase):
    def test_uninstall_full_rollback(self):
        """Assert uninstall cascades owned rows, logs, and events.

        The runtime dir stays on disk — cleanup is deferred to
        :func:`loader.boot_genomes` so the real rmtree runs in a fresh
        process where the prior Daphne's file locks are gone. See
        ``UninstallDefersDiskCleanupTest`` for the on-disk contract.
        """
        build_fake_bundle(self.scratch_root, 'gamma')
        self.install_fake('gamma')
        self.assertEqual(
            IdentityAddon.objects.filter(
                name__startswith='gamma-'
            ).count(),
            3,
        )
        modifier = NeuralModifier.objects.get(slug='gamma')
        log_pk = modifier.current_installation().pk

        deleted_slug = loader.uninstall_genome('gamma')

        self.assertEqual(deleted_slug, 'gamma')
        self.assertFalse(NeuralModifier.objects.filter(slug='gamma').exists())
        self.assertFalse(
            NeuralModifierInstallationLog.objects.filter(pk=log_pk).exists()
        )
        self.assertEqual(
            IdentityAddon.objects.filter(name__startswith='gamma-').count(),
            0,
        )


class InstallRejectsHashDriftTest(ModifierLifecycleTestCase):
    def test_install_rejects_hash_drift(self):
        """Assert hash drift on disk flips BROKEN at boot, no entry import."""
        build_fake_bundle(self.scratch_root, 'epsilon')
        self.install_fake('epsilon')

        sys.modules.pop('are_self_fake', None)

        manifest_path = self.grafts_root / 'epsilon' / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['version'] = '9.9.9'
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

        loader.boot_genomes()

        modifier = NeuralModifier.objects.get(slug='epsilon')
        self.assertEqual(modifier.status_id, NeuralModifierStatus.BROKEN)
        log = modifier.current_installation()
        hash_events = log.events.filter(
            event_type_id=NeuralModifierInstallationEventType.HASH_MISMATCH
        )
        self.assertEqual(hash_events.count(), 1)
        self.assertNotIn('are_self_fake', sys.modules)


class InstallRejectsBadImportTest(ModifierLifecycleTestCase):
    def test_install_rejects_bad_import(self):
        """Assert entry-module import failure rolls back and deletes the row."""
        build_fake_bundle(
            self.scratch_root, 'zeta', with_broken_import=True
        )

        with self.assertRaises(ImportError):
            self.install_fake('zeta')

        self.assertFalse(NeuralModifier.objects.filter(slug='zeta').exists())
        self.assertFalse((self.grafts_root / 'zeta').exists())


class InstallFlipsBrokenOnDeserializationFailureTest(ModifierLifecycleTestCase):
    def test_install_flips_broken_on_deserialization_failure(self):
        """Assert malformed modifier_data.json rolls back and deletes the row."""
        bundle = build_fake_bundle(self.scratch_root, 'bad_data')
        (bundle / 'modifier_data.json').write_text('not json')

        with self.assertRaises(Exception):
            self.install_fake('bad_data')

        self.assertFalse(
            NeuralModifier.objects.filter(slug='bad_data').exists()
        )
        self.assertFalse((self.grafts_root / 'bad_data').exists())


class InstallFileExistsDoesNotLeakRowTest(ModifierLifecycleTestCase):
    def test_install_file_exists_error_leaves_no_db_row(self):
        """Assert FileExistsError is raised with ZERO DB state persisted."""
        build_fake_bundle(self.scratch_root, 'collision')
        (self.grafts_root / 'collision').mkdir()

        with self.assertRaises(FileExistsError):
            self.install_fake('collision')

        self.assertFalse(
            NeuralModifier.objects.filter(slug='collision').exists()
        )
        self.assertEqual(
            NeuralModifierInstallationLog.objects.count(), 0
        )


class ReinstallReusesManifestPinnedPkTest(ModifierLifecycleTestCase):
    def test_reinstall_reuses_manifest_pinned_pk(self):
        """Assert reinstall after uninstall lands on the same PK declared
        in the manifest, with a fresh installation log.

        Manifest-pinned UUIDs make bundle identity stable across the
        uninstall/reinstall cycle — the row itself is freshly created
        (the prior row was deleted; its logs cascaded away), but the
        PK is preserved because the manifest declares it."""
        build_fake_bundle(self.scratch_root, 'eta')
        first = self.install_fake('eta')
        first_pk = first.pk

        loader.uninstall_genome('eta')
        # Simulate the coordinated restart: boot_genomes' orphan sweep
        # removes the runtime dir left behind by uninstall. Without
        # this, install_source_to_graft would hit its FileExistsError
        # guard and 409 — exactly the bug this machinery exists to
        # prevent in production.
        loader.boot_genomes()
        second = self.install_fake('eta')

        self.assertEqual(second.pk, first_pk)
        log_count = NeuralModifierInstallationLog.objects.filter(
            neural_modifier=second
        ).count()
        self.assertEqual(log_count, 1)


class InstallRejectsInvalidSemverTest(ModifierLifecycleTestCase):
    def test_install_rejects_invalid_semver(self):
        """Assert non-semver version rejected at manifest validation."""
        bundle = build_fake_bundle(self.scratch_root, 'bad_semver')
        manifest_path = bundle / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['version'] = 'not-semver'
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

        with self.assertRaisesRegex(ValueError, 'not valid semver'):
            self.install_fake('bad_semver')


class InstallRequiresSatisfiedTest(ModifierLifecycleTestCase):
    def test_install_requires_satisfied(self):
        """Assert install proceeds when declared requires are met."""
        build_fake_bundle(self.scratch_root, 'base_bundle')
        self.install_fake('base_bundle')

        dependent = build_fake_bundle(self.scratch_root, 'dep_bundle')
        manifest_path = dependent / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['requires'] = [
            {'slug': 'base_bundle', 'version_spec': '>=0.0.0'}
        ]
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

        self.install_fake('dep_bundle')
        self.assertEqual(
            NeuralModifier.objects.get(slug='dep_bundle').status_id,
            NeuralModifierStatus.INSTALLED,
        )


class InstallRequiresMissingTest(ModifierLifecycleTestCase):
    def test_install_requires_missing(self):
        """Assert install refuses when a required bundle is not installed."""
        bundle = build_fake_bundle(self.scratch_root, 'lonely')
        manifest_path = bundle / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['requires'] = [
            {'slug': 'ghost_bundle', 'version_spec': '>=1.0.0'}
        ]
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

        with self.assertRaisesRegex(ValueError, 'requires: not satisfied'):
            self.install_fake('lonely')


class InstallRequiresVersionMismatchTest(ModifierLifecycleTestCase):
    def test_install_requires_version_mismatch(self):
        """Assert install refuses when a required bundle is the wrong version."""
        build_fake_bundle(self.scratch_root, 'old_base')
        self.install_fake('old_base')

        dependent = build_fake_bundle(self.scratch_root, 'needs_new')
        manifest_path = dependent / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['requires'] = [
            {'slug': 'old_base', 'version_spec': '>=1.0.0'}
        ]
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

        with self.assertRaisesRegex(ValueError, 'requires: not satisfied'):
            self.install_fake('needs_new')


class UpgradeDiffTest(ModifierLifecycleTestCase):
    def test_upgrade_applies_create_update_delete(self):
        """Assert upgrade diffs owned PKs and applies create/update/delete."""
        shared_pk = str(uuid.uuid4())
        dropped_pk = str(uuid.uuid4())
        modifier_data_v1 = [
            {
                'model': 'identity.identityaddon',
                'pk': shared_pk,
                'fields': {
                    'name': 'shared',
                    'description': 'v1',
                    'addon_class_name': None,
                    'function_slug': None,
                    'phase': None,
                },
            },
            {
                'model': 'identity.identityaddon',
                'pk': dropped_pk,
                'fields': {
                    'name': 'dropped',
                    'description': 'v1',
                    'addon_class_name': None,
                    'function_slug': None,
                    'phase': None,
                },
            },
        ]
        bundle = build_fake_bundle(
            self.scratch_root, 'evolver', modifier_data=modifier_data_v1
        )
        self.install_fake('evolver')

        new_pk = str(uuid.uuid4())
        modifier_data_v2 = [
            {
                'model': 'identity.identityaddon',
                'pk': shared_pk,
                'fields': {
                    'name': 'shared',
                    'description': 'v2',
                    'addon_class_name': None,
                    'function_slug': None,
                    'phase': None,
                },
            },
            {
                'model': 'identity.identityaddon',
                'pk': new_pk,
                'fields': {
                    'name': 'brand_new',
                    'description': 'v2',
                    'addon_class_name': None,
                    'function_slug': None,
                    'phase': None,
                },
            },
        ]
        manifest_path = bundle / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['version'] = '0.0.2'
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
        (bundle / 'modifier_data.json').write_text(
            json.dumps(modifier_data_v2, indent=2) + '\n'
        )

        result = loader.upgrade_source_to_graft(bundle, 'evolver')

        self.assertEqual(result['previous_version'], '0.0.1')
        self.assertEqual(result['new_version'], '0.0.2')
        self.assertEqual(result['created'], 1)
        self.assertEqual(result['updated'], 1)
        self.assertEqual(result['deleted'], 1)

        self.assertEqual(
            IdentityAddon.objects.get(pk=shared_pk).description, 'v2'
        )
        self.assertFalse(
            IdentityAddon.objects.filter(pk=dropped_pk).exists()
        )
        self.assertTrue(IdentityAddon.objects.filter(pk=new_pk).exists())

        modifier = NeuralModifier.objects.get(slug='evolver')
        self.assertEqual(modifier.version, '0.0.2')
        # The shared row kept its genome pointer through the upgrade.
        self.assertEqual(
            IdentityAddon.objects.get(pk=shared_pk).genome_id, modifier.pk
        )


class UpgradeRefusesStaleVersionTest(ModifierLifecycleTestCase):
    def test_upgrade_refuses_same_version(self):
        """Assert upgrade refuses when on-disk version is not newer."""
        build_fake_bundle(self.scratch_root, 'samever')
        self.install_fake('samever')

        with self.assertRaisesRegex(ValueError, 'not newer'):
            loader.upgrade_source_to_graft(
                self.scratch_root / 'samever', 'samever'
            )

    def test_upgrade_allows_same_version_with_flag(self):
        """Assert --allow-same-version forces the diff to run anyway."""
        build_fake_bundle(self.scratch_root, 'samever2')
        self.install_fake('samever2')

        result = loader.upgrade_source_to_graft(
            self.scratch_root / 'samever2', 'samever2',
            allow_same_version=True,
        )
        self.assertEqual(result['previous_version'], result['new_version'])


class BootFlipsBrokenOnMissingManifestTest(ModifierLifecycleTestCase):
    def test_boot_flips_broken_on_missing_manifest(self):
        """Assert deleted manifest at boot flips BROKEN with HASH_MISMATCH event."""
        build_fake_bundle(self.scratch_root, 'manifest_gone')
        self.install_fake('manifest_gone')

        (self.grafts_root / 'manifest_gone' / 'manifest.json').unlink()
        sys.modules.pop('are_self_fake', None)

        loader.boot_genomes()

        modifier = NeuralModifier.objects.get(slug='manifest_gone')
        self.assertEqual(modifier.status_id, NeuralModifierStatus.BROKEN)
        log = modifier.current_installation()
        events = log.events.filter(
            event_type_id=NeuralModifierInstallationEventType.HASH_MISMATCH
        )
        self.assertEqual(events.count(), 1)
        self.assertIn('missing', events.first().event_data['reason'])
        self.assertNotIn('are_self_fake', sys.modules)


class BootFlipsBrokenOnMissingCodeTest(ModifierLifecycleTestCase):
    def test_boot_flips_broken_on_missing_code(self):
        """Assert deleted code/ at boot flips BROKEN with LOAD_FAILED event."""
        build_fake_bundle(self.scratch_root, 'code_gone')
        self.install_fake('code_gone')

        sys.modules.pop('are_self_fake', None)
        shutil.rmtree(self.grafts_root / 'code_gone' / 'code')

        loader.boot_genomes()

        modifier = NeuralModifier.objects.get(slug='code_gone')
        self.assertEqual(modifier.status_id, NeuralModifierStatus.BROKEN)
        log = modifier.current_installation()
        events = log.events.filter(
            event_type_id=NeuralModifierInstallationEventType.LOAD_FAILED
        )
        self.assertEqual(events.count(), 1)
        self.assertIn('traceback', events.first().event_data)


class UninstallDefersDiskCleanupTest(ModifierLifecycleTestCase):
    def test_uninstall_leaves_runtime_dir_on_disk(self):
        """Assert uninstall deletes the DB row but leaves the runtime dir.

        Inline ``rmtree`` during uninstall silently no-oped on Windows
        when the current Daphne process held live file handles on the
        bundle's code, which left the dir on disk and produced a 409 on
        the next install. Cleanup now defers to
        :func:`loader.boot_genomes` in a fresh process.
        """
        build_fake_bundle(self.scratch_root, 'deferred')
        self.install_fake('deferred')
        runtime = self.grafts_root / 'deferred'
        self.assertTrue(runtime.is_dir())

        loader.uninstall_genome('deferred')

        self.assertFalse(
            NeuralModifier.objects.filter(slug='deferred').exists()
        )
        self.assertTrue(
            runtime.is_dir(),
            'Runtime dir must persist — cleanup is deferred to boot.',
        )


class BootBundlesSweepsOrphanDirsTest(ModifierLifecycleTestCase):
    def test_boot_bundles_removes_orphan_dir(self):
        """Assert boot_genomes() deletes grafts dirs with no matching DB row."""
        orphan = self.grafts_root / 'orphan'
        orphan.mkdir()
        (orphan / 'stub.txt').write_text('payload')

        loader.boot_genomes()

        self.assertFalse(orphan.exists())


class BootBundlesPreservesInstalledDirsTest(ModifierLifecycleTestCase):
    def test_boot_bundles_preserves_installed_bundle(self):
        """Assert boot_genomes() keeps dirs whose slug has a DB row."""
        build_fake_bundle(self.scratch_root, 'keeper')
        modifier = self.install_fake('keeper')
        status_before = modifier.status_id

        loader.boot_genomes()

        modifier.refresh_from_db()
        self.assertTrue((self.grafts_root / 'keeper').is_dir())
        self.assertEqual(modifier.status_id, status_before)


class BootBundlesSkipsMissingTableTest(ModifierLifecycleTestCase):
    def test_boot_bundles_skips_missing_table(self):
        """Assert boot_genomes returns silently when DB is not ready."""
        from unittest.mock import patch

        from django.db import OperationalError

        runtime_bundle = self.grafts_root / 'kappa'
        runtime_bundle.mkdir(parents=True)
        (runtime_bundle / 'manifest.json').write_text('{}')

        target = (
            'neuroplasticity.loader.iter_installed_genomes'
        )
        with patch(target, side_effect=OperationalError('test')):
            loader.boot_genomes()


class InstallFromArchiveClearsOperatingRoomTest(ModifierLifecycleTestCase):
    def test_install_from_archive_clears_operating_room(self):
        """Assert operating_room is empty after a successful archive install."""
        archive = build_fake_bundle_archive(self.genomes_root, 'or_happy')

        loader.install_genome_to_graft(archive)

        self.assertEqual(list(self.operating_room_root.iterdir()), [])
        self.assertTrue((self.grafts_root / 'or_happy').is_dir())


class InstallFromArchiveClearsOperatingRoomOnFailureTest(
    ModifierLifecycleTestCase
):
    def test_operating_room_clean_after_failed_install(self):
        """Assert operating_room is empty after a failed archive install."""
        import zipfile
        scratch = self._tmp_root / 'broken_src'
        (scratch / 'unreal_broken').mkdir(parents=True)
        (scratch / 'unreal_broken' / 'manifest.json').write_text('{}')
        archive = self.genomes_root / 'unreal_broken.zip'
        with zipfile.ZipFile(archive, 'w') as zf:
            zf.write(
                scratch / 'unreal_broken' / 'manifest.json',
                'unreal_broken/manifest.json',
            )

        with self.assertRaises(Exception):
            loader.install_genome_to_graft(archive)

        self.assertEqual(list(self.operating_room_root.iterdir()), [])
        self.assertFalse(
            NeuralModifier.objects.filter(slug='unreal_broken').exists()
        )


class SaveBundleRoundTripTest(ModifierLifecycleTestCase):
    """Install → save → uninstall → reinstall should converge to the same
    owned-row set. Exercises Deliverable 3."""

    def test_save_round_trip(self):
        build_fake_bundle(self.scratch_root, 'saver')
        modifier = self.install_fake('saver')
        before_pks = set(
            IdentityAddon.objects.filter(genome=modifier).values_list(
                'pk', flat=True
            )
        )
        self.assertEqual(len(before_pks), 3)

        result = loader.save_graft_to_genome('saver')
        self.assertEqual(result['slug'], 'saver')
        self.assertEqual(result['row_count'], 3)
        self.assertTrue(Path(result['zip_path']).exists())
        self.assertGreater(result['bytes_written'], 0)

        # Round trip — uninstall, reinstall from the freshly written zip.
        loader.uninstall_genome('saver')
        self.assertFalse(
            NeuralModifier.objects.filter(slug='saver').exists()
        )
        # Simulate the coordinated restart: boot_genomes' orphan sweep
        # clears the deferred runtime dir before the archive reinstall.
        loader.boot_genomes()
        archive = Path(result['zip_path'])
        loader.install_genome_to_graft(archive)

        modifier2 = NeuralModifier.objects.get(slug='saver')
        after_pks = set(
            IdentityAddon.objects.filter(genome=modifier2).values_list(
                'pk', flat=True
            )
        )
        self.assertEqual(before_pks, after_pks)


class SaveBundleMediaRoundTripTest(ModifierLifecycleTestCase):
    """Assert grafts/<slug>/media/ rides the save→install zip round-trip."""

    fixtures = list(ModifierLifecycleTestCase.fixtures) + [
        'identity/fixtures/genetic_immutables.json',
    ]

    def test_media_baked_into_archive_and_restored_on_install(self):
        build_fake_bundle(self.scratch_root, 'painter')
        modifier = self.install_fake('painter')

        # Drop a display=FILE Avatar row owned by the bundle plus its
        # bytes under grafts/painter/media/. The save side should
        # mirror the bytes into the archive at painter/media/.
        avatar = Avatar.objects.create(
            name='Painter Avatar',
            display_id=AvatarSelectedDisplayType.FILE,
            genome=modifier,
        )
        avatar.original_filename = 'face.png'
        avatar.stored_filename = f'{avatar.id}.png'
        avatar.save()
        media_dir = self.grafts_root / 'painter' / 'media'
        media_dir.mkdir(parents=True, exist_ok=True)
        bytes_payload = b'\x89PNG\r\n\x1a\nFAKEBYTES'
        (media_dir / avatar.stored_filename).write_bytes(bytes_payload)

        result = loader.save_graft_to_genome('painter')
        archive = Path(result['zip_path'])
        self.assertTrue(archive.exists())

        # The zip must contain painter/media/<filename>.
        with zipfile.ZipFile(archive) as zf:
            names = set(zf.namelist())
            arc_name = f'painter/media/{avatar.stored_filename}'
            self.assertIn(arc_name, names)
            self.assertEqual(zf.read(arc_name), bytes_payload)

        # Round-trip: uninstall, sweep, reinstall — bytes must land
        # back at grafts/painter/media/<filename>, and the Avatar row
        # must be re-stamped with the bundle's genome.
        loader.uninstall_genome('painter')
        self.assertFalse(
            NeuralModifier.objects.filter(slug='painter').exists()
        )
        loader.boot_genomes()
        loader.install_genome_to_graft(archive)

        restored = NeuralModifier.objects.get(slug='painter')
        restored_avatar = Avatar.objects.get(pk=avatar.pk)
        self.assertEqual(restored_avatar.genome_id, restored.pk)
        self.assertEqual(restored_avatar.stored_filename, avatar.stored_filename)

        restored_path = (
            self.grafts_root
            / 'painter'
            / 'media'
            / restored_avatar.stored_filename
        )
        self.assertTrue(restored_path.exists())
        self.assertEqual(restored_path.read_bytes(), bytes_payload)
