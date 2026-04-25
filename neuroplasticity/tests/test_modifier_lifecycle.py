"""Lifecycle tests for the NeuralModifier loader and management commands.

Covers install / enable / disable / uninstall happy paths plus the two
BROKEN failure modes (manifest hash drift, entry-module import failure).
Tests build self-contained fake bundles in a tmp directory and override
the three root settings, so the committed Unreal bundle is never touched.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import textwrap
import uuid
from pathlib import Path
from typing import Iterable, Optional

from django.core.management import call_command
from django.test import TestCase, override_settings

from hypothalamus.models import AIModelTags
from neuroplasticity import loader
from neuroplasticity.models import (
    NeuralModifier,
    NeuralModifierContribution,
    NeuralModifierInstallationEvent,
    NeuralModifierInstallationEventType,
    NeuralModifierInstallationLog,
    NeuralModifierStatus,
)


def _make_tag_payload(name: str) -> dict:
    """Serialized AIModelTags row — UUID PK, no FK dependencies."""
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
    """Build a synthetic bundle in a tmp dir and zip it into the genomes dir.

    Returns the path to the created ``<slug>.zip``. Used by the
    archive-based install tests.
    """
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

    The default `entry_modules=('are_self_fake',)` and `namespace_pkg=None`
    pair create a `code/are_self_fake/` Python package that imports cleanly.
    Pass `with_broken_import=True` to make the entry module raise ImportError
    at import time.
    """
    if modifier_data is None:
        modifier_data = [
            _make_tag_payload('{0}-alpha-{1}'.format(slug, uuid.uuid4().hex[:8])),
            _make_tag_payload('{0}-beta-{1}'.format(slug, uuid.uuid4().hex[:8])),
            _make_tag_payload('{0}-gamma-{1}'.format(slug, uuid.uuid4().hex[:8])),
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
    """Base class — wires tmp roots, loads neuroplasticity reference data.

    Each test uses its own tmp_path for genomes + grafts + operating_room
    so concurrent tests do not collide and the committed Unreal bundle
    is never reached.

    ``self.scratch_root`` is where tests build fake directory bundles;
    ``self.genomes_root`` is where archive-based tests drop zips.
    """

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

    # Convenience used pervasively by tests that build a directory
    # bundle and want to install it without zipping first. Wraps the
    # loader primitive so one line covers the common case.
    def install_fake(self, slug: str) -> NeuralModifier:
        return loader.install_bundle_from_source(
            self.scratch_root / slug, slug
        )


class InstallHappyPathTest(ModifierLifecycleTestCase):
    def test_install_happy_path(self):
        """Assert install creates contribution rows, copies disk, fires INSTALL event."""
        build_fake_bundle(self.scratch_root, 'alpha')

        modifier = self.install_fake('alpha')

        self.assertEqual(modifier.status_id, NeuralModifierStatus.INSTALLED)
        self.assertEqual(modifier.contributions.count(), 3)
        self.assertEqual(AIModelTags.objects.filter(name__startswith='alpha-').count(), 3)
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
        self.assertEqual(events[0].event_data['contributions'], 3)


class EnableDisableRoundTripTest(ModifierLifecycleTestCase):
    def test_enable_disable_round_trip(self):
        """Assert enable/disable flips status and writes one event per call."""
        build_fake_bundle(self.scratch_root, 'beta')
        self.install_fake('beta')

        loader.enable_bundle('beta')
        modifier = NeuralModifier.objects.get(slug='beta')
        self.assertEqual(modifier.status_id, NeuralModifierStatus.ENABLED)

        loader.disable_bundle('beta')
        modifier.refresh_from_db()
        self.assertEqual(modifier.status_id, NeuralModifierStatus.DISABLED)

        loader.enable_bundle('beta')
        modifier.refresh_from_db()
        self.assertEqual(modifier.status_id, NeuralModifierStatus.ENABLED)

        log = modifier.current_installation()
        event_types = [e.event_type_id for e in log.events.order_by('created')]
        # INSTALL, then ENABLE, DISABLE, ENABLE.
        self.assertIn(NeuralModifierInstallationEventType.ENABLE, event_types)
        self.assertIn(NeuralModifierInstallationEventType.DISABLE, event_types)
        self.assertEqual(
            event_types.count(NeuralModifierInstallationEventType.ENABLE), 2
        )


class UninstallFullRollbackTest(ModifierLifecycleTestCase):
    def test_uninstall_full_rollback(self):
        """Assert uninstall deletes targets, contribution rows, runtime dir, and row."""
        build_fake_bundle(self.scratch_root, 'gamma')
        self.install_fake('gamma')
        self.assertEqual(
            AIModelTags.objects.filter(name__startswith='gamma-').count(), 3
        )
        modifier = NeuralModifier.objects.get(slug='gamma')
        log_pk = modifier.current_installation().pk

        deleted_slug = loader.uninstall_bundle('gamma')

        # AVAILABLE = no DB row. Uninstall deletes the NeuralModifier
        # row entirely; contributions, logs, and events cascade.
        self.assertEqual(deleted_slug, 'gamma')
        self.assertFalse(NeuralModifier.objects.filter(slug='gamma').exists())
        self.assertEqual(NeuralModifierContribution.objects.count(), 0)
        self.assertFalse(
            NeuralModifierInstallationLog.objects.filter(pk=log_pk).exists()
        )
        self.assertEqual(
            AIModelTags.objects.filter(name__startswith='gamma-').count(), 0
        )
        self.assertFalse((self.grafts_root / 'gamma').exists())


class UninstallEventCapturesOrphansBeforeDeleteTest(ModifierLifecycleTestCase):
    def test_single_out_of_band_orphan(self):
        """Assert out-of-band target deletion names the orphan in the event."""
        build_fake_bundle(self.scratch_root, 'delta')
        self.install_fake('delta')
        target = AIModelTags.objects.filter(name__startswith='delta-').first()
        expected_orphan_id = str(target.pk)
        target.delete()

        payload = _capture_uninstall_event_payload(self, 'delta')

        self.assertEqual(payload['contributions_total'], 3)
        self.assertEqual(payload['contributions_resolved'], 2)
        self.assertEqual(payload['orphaned_ids'], [expected_orphan_id])
        self.assertEqual(payload['contributions_unresolved'], [])
        self.assertFalse(NeuralModifier.objects.filter(slug='delta').exists())

    def test_multiple_out_of_band_orphans(self):
        """Assert every out-of-band-deleted target shows up in orphaned_ids.

        Reads the event payload via a ``_log_event`` hook because the
        UNINSTALL event, its log, and the NeuralModifier row are all
        gone by the time ``uninstall_bundle`` returns (CASCADE).
        """
        build_fake_bundle(self.scratch_root, 'mu')
        self.install_fake('mu')
        targets = list(AIModelTags.objects.filter(name__startswith='mu-'))
        expected_orphans = {str(t.pk) for t in targets[:2]}
        for t in targets[:2]:
            t.delete()

        payload = _capture_uninstall_event_payload(self, 'mu')

        self.assertEqual(payload['contributions_total'], 3)
        self.assertEqual(payload['contributions_resolved'], 1)
        self.assertEqual(set(payload['orphaned_ids']), expected_orphans)
        self.assertEqual(payload['contributions_unresolved'], [])


def _capture_uninstall_event_payload(testcase, slug: str) -> dict:
    """Helper: intercept the UNINSTALL event emission during uninstall_bundle.

    Patches `_log_event` for the duration of the call and returns the
    event_data dict for the UNINSTALL event. Raises if no UNINSTALL
    event is emitted — a sign that uninstall silently skipped the path.
    """
    from unittest.mock import patch
    captured = {}
    real_log_event = loader._log_event

    def _recording_log_event(log, event_type_id, event_data):
        if event_type_id == NeuralModifierInstallationEventType.UNINSTALL:
            captured.update(event_data)
        return real_log_event(log, event_type_id, event_data)

    with patch.object(loader, '_log_event', side_effect=_recording_log_event):
        loader.uninstall_bundle(slug)

    if not captured:
        raise AssertionError('UNINSTALL event was never emitted')
    return captured


class UninstallCleanInstallEmitsZeroOrphansTest(ModifierLifecycleTestCase):
    def test_clean_install_uninstall_round_trip_emits_zero_orphans(self):
        """Assert FK-cascade dependencies don't leak as false orphans.

        Direct repro of the 53/260 bug: pre-fix, cascade-deleted siblings
        surfaced as 'orphaned' even on a clean install/uninstall round
        trip. Post-fix, only out-of-band deletions count as orphans.
        """
        # AIModel (parent) + two AIModelRating children (CASCADE on ai_model
        # FK). All three are bundle contributions; reverse-iter visits the
        # children first, but the snapshot logic must report 0 orphans
        # regardless of which row's deletion incidentally cascades.
        model_pk = str(uuid.uuid4())
        rating_pk_1 = str(uuid.uuid4())
        rating_pk_2 = str(uuid.uuid4())
        # Deserialization bypasses auto_now / auto_now_add, so `created`
        # and `modified` must be supplied explicitly for any model that
        # inherits Created/Modified mixins.
        ts = '2026-04-19T00:00:00Z'
        modifier_data = [
            {
                'model': 'hypothalamus.aimodel',
                'pk': model_pk,
                'fields': {
                    'name': 'cascade-test-model',
                    'description': 'Parent of cascade chain.',
                    'context_length': 1000,
                    'enabled': True,
                },
            },
            {
                'model': 'hypothalamus.aimodelrating',
                'pk': rating_pk_1,
                'fields': {
                    'ai_model': model_pk,
                    'elo_score': 1200.0,
                    'arena_battles': 1,
                    'source_leaderboard': 'test',
                    'is_current': True,
                    'created': ts,
                },
            },
            {
                'model': 'hypothalamus.aimodelrating',
                'pk': rating_pk_2,
                'fields': {
                    'ai_model': model_pk,
                    'elo_score': 1300.0,
                    'arena_battles': 2,
                    'source_leaderboard': 'test',
                    'is_current': False,
                    'created': ts,
                },
            },
        ]
        build_fake_bundle(
            self.scratch_root, 'cascadia', modifier_data=modifier_data
        )
        self.install_fake('cascadia')
        modifier = NeuralModifier.objects.get(slug='cascadia')
        self.assertEqual(modifier.contributions.count(), 3)

        # Force the parent contribution to sort FIRST under reverse-created
        # order so the loop encounters AIModel before its AIModelRatings —
        # AIModel.delete() then cascade-removes the ratings before the loop
        # reaches them. Pre-fix this surfaced as 'orphans'; post-fix it
        # must read as 'resolved'.
        import datetime as _dt
        parent_contribution = modifier.contributions.get(object_id=model_pk)
        parent_contribution.created = parent_contribution.created + _dt.timedelta(
            seconds=10
        )
        # `created` is auto_now_add, so save() does NOT bypass that. Use update().
        NeuralModifierContribution.objects.filter(pk=parent_contribution.pk).update(
            created=parent_contribution.created
        )

        payload = _capture_uninstall_event_payload(self, 'cascadia')
        self.assertEqual(payload['contributions_total'], 3)
        self.assertEqual(payload['orphaned_ids'], [])
        self.assertEqual(payload['contributions_unresolved'], [])
        self.assertEqual(payload['contributions_resolved'], 3)


class InstallRejectsHashDriftTest(ModifierLifecycleTestCase):
    def test_install_rejects_hash_drift(self):
        """Assert hash drift on disk flips BROKEN at boot, no entry import."""
        build_fake_bundle(self.scratch_root, 'epsilon')
        self.install_fake('epsilon')

        # Drop the imported module so we can detect a re-import attempt.
        sys.modules.pop('are_self_fake', None)

        # Mutate the on-disk manifest so its hash diverges.
        manifest_path = self.grafts_root / 'epsilon' / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['version'] = '9.9.9'
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

        loader.boot_bundles()

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
        """Assert entry-module import failure rolls back and deletes the row.

        Fresh install failure leaves NO DB row behind — AVAILABLE = no row.
        """
        build_fake_bundle(
            self.scratch_root, 'zeta', with_broken_import=True
        )

        with self.assertRaises(ImportError):
            self.install_fake('zeta')

        # Row was deleted on failure: bundle is back to AVAILABLE.
        self.assertFalse(NeuralModifier.objects.filter(slug='zeta').exists())
        self.assertEqual(NeuralModifierContribution.objects.count(), 0)
        # Runtime dir cleaned up by the except branch.
        self.assertFalse((self.grafts_root / 'zeta').exists())


class InstallFlipsBrokenOnDeserializationFailureTest(ModifierLifecycleTestCase):
    def test_install_flips_broken_on_deserialization_failure(self):
        """Assert malformed modifier_data.json rolls back and deletes the row."""
        bundle = build_fake_bundle(self.scratch_root, 'bad_data')
        # Corrupt the source bundle's modifier_data.json so the copy in
        # runtime is also corrupt — guarantees serializers.deserialize
        # raises during the install's atomic block.
        (bundle / 'modifier_data.json').write_text('not json')

        with self.assertRaises(Exception):
            self.install_fake('bad_data')

        # Row was deleted on failure: bundle is back to AVAILABLE.
        self.assertFalse(
            NeuralModifier.objects.filter(slug='bad_data').exists()
        )
        self.assertEqual(NeuralModifierContribution.objects.count(), 0)
        # Runtime dir cleaned up by the except branch.
        self.assertFalse((self.grafts_root / 'bad_data').exists())


class InstallFileExistsDoesNotLeakRowTest(ModifierLifecycleTestCase):
    def test_install_file_exists_error_leaves_no_db_row(self):
        """Assert FileExistsError is raised with ZERO DB state persisted.

        The runtime-dir collision check runs BEFORE any modifier row is
        created, so a failed pre-flight never leaves a bogus DB row.
        """
        build_fake_bundle(self.scratch_root, 'collision')
        # Pre-create the graft dir to simulate a stale runtime tree.
        (self.grafts_root / 'collision').mkdir()

        with self.assertRaises(FileExistsError):
            self.install_fake('collision')

        self.assertFalse(
            NeuralModifier.objects.filter(slug='collision').exists()
        )
        self.assertEqual(
            NeuralModifierInstallationLog.objects.count(), 0
        )


class ReinstallCreatesFreshRowTest(ModifierLifecycleTestCase):
    def test_reinstall_creates_fresh_row(self):
        """Assert reinstall after uninstall yields a fresh NeuralModifier row.

        Uninstall deletes the row, so reinstall is a brand-new row with
        a brand-new installation log — not a reuse of the old one.
        """
        build_fake_bundle(self.scratch_root, 'eta')
        first = self.install_fake('eta')
        first_pk = first.pk

        loader.uninstall_bundle('eta')
        second = self.install_fake('eta')

        # Fresh row — the old row was deleted.
        self.assertNotEqual(second.pk, first_pk)
        log_count = NeuralModifierInstallationLog.objects.filter(
            neural_modifier=second
        ).count()
        # Fresh install = 1 log on the new row.
        self.assertEqual(log_count, 1)


class ListModifiersReportsStatusTest(ModifierLifecycleTestCase):
    def test_list_modifiers_reports_status(self):
        """Assert list_modifiers prints each slug + status."""
        build_fake_bundle(self.scratch_root, 'theta')
        build_fake_bundle(self.scratch_root, 'iota')
        self.install_fake('theta')
        self.install_fake('iota')
        loader.enable_bundle('iota')

        out = io.StringIO()
        call_command('list_modifiers', stdout=out)
        printed = out.getvalue()
        self.assertIn('theta', printed)
        self.assertIn('iota', printed)
        self.assertIn('Installed', printed)
        self.assertIn('Enabled', printed)


# TASK 15: semver, requires, upgrade-diff coverage.
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


class UpgradePreservesUnchangedContributionsTest(ModifierLifecycleTestCase):
    def test_upgrade_preserves_unchanged(self):
        """Assert upgrade preserves shared PKs, deletes dropped, creates new."""
        shared_pk = str(uuid.uuid4())
        dropped_pk = str(uuid.uuid4())
        modifier_data_v1 = [
            {
                'model': 'hypothalamus.aimodeltags',
                'pk': shared_pk,
                'fields': {'name': 'shared', 'description': 'v1'},
            },
            {
                'model': 'hypothalamus.aimodeltags',
                'pk': dropped_pk,
                'fields': {'name': 'dropped', 'description': 'v1'},
            },
        ]
        bundle = build_fake_bundle(
            self.scratch_root, 'evolver', modifier_data=modifier_data_v1
        )
        self.install_fake('evolver')

        shared_contribution_pk = NeuralModifierContribution.objects.get(
            object_id=shared_pk
        ).pk

        # Rewrite the SOURCE bundle to v0.0.2:
        #   - shared_pk: updated description
        #   - dropped_pk: gone
        #   - new_pk:     new row
        new_pk = str(uuid.uuid4())
        modifier_data_v2 = [
            {
                'model': 'hypothalamus.aimodeltags',
                'pk': shared_pk,
                'fields': {'name': 'shared', 'description': 'v2'},
            },
            {
                'model': 'hypothalamus.aimodeltags',
                'pk': new_pk,
                'fields': {'name': 'brand_new', 'description': 'v2'},
            },
        ]
        manifest_path = bundle / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['version'] = '0.0.2'
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
        (bundle / 'modifier_data.json').write_text(
            json.dumps(modifier_data_v2, indent=2) + '\n'
        )

        result = loader.upgrade_bundle_from_source(bundle, 'evolver')

        self.assertEqual(result['previous_version'], '0.0.1')
        self.assertEqual(result['new_version'], '0.0.2')
        self.assertEqual(result['created'], 1)
        self.assertEqual(result['updated'], 1)
        self.assertEqual(result['deleted'], 1)

        self.assertEqual(
            NeuralModifierContribution.objects.get(
                object_id=shared_pk
            ).pk,
            shared_contribution_pk,
        )
        self.assertEqual(
            AIModelTags.objects.get(pk=shared_pk).description, 'v2'
        )
        self.assertFalse(
            AIModelTags.objects.filter(pk=dropped_pk).exists()
        )
        self.assertTrue(AIModelTags.objects.filter(pk=new_pk).exists())
        self.assertTrue(
            NeuralModifierContribution.objects.filter(
                object_id=new_pk
            ).exists()
        )

        modifier = NeuralModifier.objects.get(slug='evolver')
        self.assertEqual(modifier.version, '0.0.2')
        log = modifier.current_installation()
        upgrade_event = log.events.get(
            event_type_id=NeuralModifierInstallationEventType.UPGRADE
        )
        payload = upgrade_event.event_data
        self.assertEqual(payload['previous_version'], '0.0.1')
        self.assertEqual(payload['new_version'], '0.0.2')
        self.assertEqual(payload['created'], 1)
        self.assertEqual(payload['updated'], 1)
        self.assertEqual(payload['deleted'], 1)


class UpgradeRefusesStaleVersionTest(ModifierLifecycleTestCase):
    def test_upgrade_refuses_same_version(self):
        """Assert upgrade refuses when on-disk version is not newer."""
        build_fake_bundle(self.scratch_root, 'samever')
        self.install_fake('samever')

        with self.assertRaisesRegex(ValueError, 'not newer'):
            loader.upgrade_bundle_from_source(
                self.scratch_root / 'samever', 'samever'
            )

    def test_upgrade_allows_same_version_with_flag(self):
        """Assert --allow-same-version forces the diff to run anyway."""
        build_fake_bundle(self.scratch_root, 'samever2')
        self.install_fake('samever2')

        result = loader.upgrade_bundle_from_source(
            self.scratch_root / 'samever2', 'samever2',
            allow_same_version=True,
        )
        self.assertEqual(result['previous_version'], result['new_version'])


# TASK 11: Mode B/C/D BROKEN-transition coverage. Mode A is
# InstallRejectsHashDriftTest above; Mode D rides the install path, the
# other two ride boot.
class BootFlipsBrokenOnMissingManifestTest(ModifierLifecycleTestCase):
    def test_boot_flips_broken_on_missing_manifest(self):
        """Assert deleted manifest at boot flips BROKEN with HASH_MISMATCH event."""
        build_fake_bundle(self.scratch_root, 'manifest_gone')
        self.install_fake('manifest_gone')

        (self.grafts_root / 'manifest_gone' / 'manifest.json').unlink()
        sys.modules.pop('are_self_fake', None)

        loader.boot_bundles()

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

        loader.boot_bundles()

        modifier = NeuralModifier.objects.get(slug='code_gone')
        self.assertEqual(modifier.status_id, NeuralModifierStatus.BROKEN)
        log = modifier.current_installation()
        events = log.events.filter(
            event_type_id=NeuralModifierInstallationEventType.LOAD_FAILED
        )
        self.assertEqual(events.count(), 1)
        self.assertIn('traceback', events.first().event_data)


class BootBundlesSkipsMissingTableTest(ModifierLifecycleTestCase):
    def test_boot_bundles_skips_missing_table(self):
        """Assert boot_bundles returns silently when DB is not ready."""
        from unittest.mock import patch

        from django.db import OperationalError

        # Place a bundle on disk so the function would otherwise try to walk it.
        runtime_bundle = self.grafts_root / 'kappa'
        runtime_bundle.mkdir(parents=True)
        (runtime_bundle / 'manifest.json').write_text('{}')

        target = (
            'neuroplasticity.loader.iter_installed_bundles'
        )
        with patch(target, side_effect=OperationalError('test')):
            # Must not raise.
            loader.boot_bundles()


class InstallFromArchiveClearsOperatingRoomTest(ModifierLifecycleTestCase):
    def test_install_from_archive_clears_operating_room(self):
        """Assert operating_room is empty after a successful archive install."""
        archive = build_fake_bundle_archive(self.genomes_root, 'or_happy')

        loader.install_bundle_from_archive(archive)

        self.assertEqual(list(self.operating_room_root.iterdir()), [])
        self.assertTrue((self.grafts_root / 'or_happy').is_dir())


class InstallFromArchiveClearsOperatingRoomOnFailureTest(
    ModifierLifecycleTestCase
):
    def test_operating_room_clean_after_failed_install(self):
        """Assert operating_room is empty after a failed archive install.

        Corrupt the archive's manifest so install raises mid-flight;
        the finally-cleanup must still nuke the extraction tempdir.
        """
        # Build a syntactically-valid zip whose manifest is missing keys.
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
            loader.install_bundle_from_archive(archive)

        self.assertEqual(list(self.operating_room_root.iterdir()), [])
        self.assertFalse(
            NeuralModifier.objects.filter(slug='unreal_broken').exists()
        )
