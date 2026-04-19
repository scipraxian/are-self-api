"""Lifecycle tests for the NeuralModifier loader and management commands.

Covers install / enable / disable / uninstall happy paths plus the two
BROKEN failure modes (manifest hash drift, entry-module import failure).
Tests build self-contained fake bundles in a tmp directory and override
MODIFIER_GENOME_ROOT / NEURAL_MODIFIERS_ROOT, so the real
modifier_genome/unreal bundle is never touched.
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


def build_fake_bundle(
    genome_root: Path,
    slug: str,
    *,
    modifier_data: Optional[list] = None,
    entry_modules: Iterable[str] = ('are_self_fake',),
    with_broken_import: bool = False,
    namespace_pkg: Optional[str] = None,
) -> Path:
    """Write a minimal valid-shape bundle into genome_root/<slug>/.

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
    bundle = genome_root / slug
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

    Each test uses its own tmp_path for genome + runtime so concurrent
    tests do not collide and the real `modifier_genome/unreal` bundle is
    never reached.
    """

    fixtures = ['neuroplasticity/fixtures/genetic_immutables.json']

    def setUp(self):
        super().setUp()
        self._tmp_root = Path(tempfile.mkdtemp(prefix='neuroplasticity-test-'))
        self.genome_root = self._tmp_root / 'modifier_genome'
        self.runtime_root = self._tmp_root / 'neural_modifiers'
        self.genome_root.mkdir()
        self._sys_path_snapshot = list(sys.path)
        self._sys_modules_snapshot = set(sys.modules.keys())
        self._settings_override = override_settings(
            MODIFIER_GENOME_ROOT=str(self.genome_root),
            NEURAL_MODIFIERS_ROOT=str(self.runtime_root),
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


class InstallHappyPathTest(ModifierLifecycleTestCase):
    def test_install_happy_path(self):
        """Assert install creates contribution rows, copies disk, fires INSTALL event."""
        build_fake_bundle(self.genome_root, 'alpha')

        modifier = loader.install_bundle('alpha')

        self.assertEqual(modifier.status_id, NeuralModifierStatus.INSTALLED)
        self.assertEqual(modifier.contributions.count(), 3)
        self.assertEqual(AIModelTags.objects.filter(name__startswith='alpha-').count(), 3)
        self.assertEqual(modifier.name, 'Fake alpha')
        self.assertTrue((self.runtime_root / 'alpha').is_dir())
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
        build_fake_bundle(self.genome_root, 'beta')
        loader.install_bundle('beta')

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
        """Assert uninstall deletes targets, contribution rows, runtime dir."""
        build_fake_bundle(self.genome_root, 'gamma')
        loader.install_bundle('gamma')
        self.assertEqual(
            AIModelTags.objects.filter(name__startswith='gamma-').count(), 3
        )

        modifier = loader.uninstall_bundle('gamma')

        self.assertEqual(modifier.status_id, NeuralModifierStatus.DISCOVERED)
        self.assertEqual(modifier.contributions.count(), 0)
        self.assertEqual(
            AIModelTags.objects.filter(name__startswith='gamma-').count(), 0
        )
        self.assertFalse((self.runtime_root / 'gamma').exists())
        self.assertTrue(NeuralModifier.objects.filter(slug='gamma').exists())
        log = modifier.current_installation()
        uninstall_events = log.events.filter(
            event_type_id=NeuralModifierInstallationEventType.UNINSTALL
        )
        self.assertEqual(uninstall_events.count(), 1)
        payload = uninstall_events.first().event_data
        self.assertEqual(payload['contributions_total'], 3)
        self.assertEqual(payload['contributions_resolved'], 3)
        self.assertEqual(payload['orphaned_ids'], [])


class UninstallHandlesOrphanedContributionTest(ModifierLifecycleTestCase):
    def test_uninstall_handles_orphaned_contribution(self):
        """Assert out-of-band target deletion names the orphan in the event."""
        build_fake_bundle(self.genome_root, 'delta')
        loader.install_bundle('delta')

        # Out-of-band delete: drop one of the contribution targets directly.
        target = AIModelTags.objects.filter(name__startswith='delta-').first()
        expected_orphan_id = str(target.pk)
        target.delete()

        modifier = loader.uninstall_bundle('delta')

        self.assertEqual(modifier.status_id, NeuralModifierStatus.DISCOVERED)
        self.assertEqual(modifier.contributions.count(), 0)
        log = modifier.current_installation()
        uninstall_event = log.events.get(
            event_type_id=NeuralModifierInstallationEventType.UNINSTALL
        )
        self.assertEqual(uninstall_event.event_data['contributions_total'], 3)
        self.assertEqual(uninstall_event.event_data['contributions_resolved'], 2)
        self.assertEqual(
            uninstall_event.event_data['orphaned_ids'], [expected_orphan_id]
        )


class UninstallCapturesAllOrphanedIdsTest(ModifierLifecycleTestCase):
    def test_uninstall_captures_all_orphaned_ids(self):
        """Assert every out-of-band-deleted target shows up in orphaned_ids."""
        build_fake_bundle(self.genome_root, 'mu')
        loader.install_bundle('mu')

        # Out-of-band delete two of the three targets.
        targets = list(AIModelTags.objects.filter(name__startswith='mu-'))
        expected_orphans = {str(t.pk) for t in targets[:2]}
        for t in targets[:2]:
            t.delete()

        modifier = loader.uninstall_bundle('mu')

        log = modifier.current_installation()
        uninstall_event = log.events.get(
            event_type_id=NeuralModifierInstallationEventType.UNINSTALL
        )
        payload = uninstall_event.event_data
        self.assertEqual(payload['contributions_total'], 3)
        self.assertEqual(payload['contributions_resolved'], 1)
        self.assertEqual(set(payload['orphaned_ids']), expected_orphans)


class InstallRejectsHashDriftTest(ModifierLifecycleTestCase):
    def test_install_rejects_hash_drift(self):
        """Assert hash drift on disk flips BROKEN at boot, no entry import."""
        build_fake_bundle(self.genome_root, 'epsilon')
        loader.install_bundle('epsilon')

        # Drop the imported module so we can detect a re-import attempt.
        sys.modules.pop('are_self_fake', None)

        # Mutate the on-disk manifest so its hash diverges.
        manifest_path = self.runtime_root / 'epsilon' / 'manifest.json'
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
        """Assert entry-module import failure rolls back contributions, flips BROKEN."""
        build_fake_bundle(
            self.genome_root, 'zeta', with_broken_import=True
        )

        with self.assertRaises(ImportError):
            loader.install_bundle('zeta')

        modifier = NeuralModifier.objects.get(slug='zeta')
        self.assertEqual(modifier.status_id, NeuralModifierStatus.BROKEN)
        # No contribution rows: the atomic block rolled back.
        self.assertEqual(modifier.contributions.count(), 0)
        # No copied runtime dir: cleanup ran in the except branch.
        self.assertFalse((self.runtime_root / 'zeta').exists())
        # InstallationLog exists, with a LOAD_FAILED event carrying the traceback.
        log = modifier.current_installation()
        load_failed = log.events.filter(
            event_type_id=NeuralModifierInstallationEventType.LOAD_FAILED
        )
        self.assertEqual(load_failed.count(), 1)
        self.assertIn('test-injected import failure', load_failed.first().event_data['traceback'])


# TASK 11: Mode B/C/D BROKEN-transition coverage. Mode A is
# InstallRejectsHashDriftTest above; Mode D rides the install path, the
# other two ride boot.
class BootFlipsBrokenOnMissingManifestTest(ModifierLifecycleTestCase):
    def test_boot_flips_broken_on_missing_manifest(self):
        """Assert deleted manifest at boot flips BROKEN with HASH_MISMATCH event."""
        build_fake_bundle(self.genome_root, 'manifest_gone')
        loader.install_bundle('manifest_gone')

        (self.runtime_root / 'manifest_gone' / 'manifest.json').unlink()
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
        build_fake_bundle(self.genome_root, 'code_gone')
        loader.install_bundle('code_gone')

        sys.modules.pop('are_self_fake', None)
        shutil.rmtree(self.runtime_root / 'code_gone' / 'code')

        loader.boot_bundles()

        modifier = NeuralModifier.objects.get(slug='code_gone')
        self.assertEqual(modifier.status_id, NeuralModifierStatus.BROKEN)
        log = modifier.current_installation()
        events = log.events.filter(
            event_type_id=NeuralModifierInstallationEventType.LOAD_FAILED
        )
        self.assertEqual(events.count(), 1)
        self.assertIn('traceback', events.first().event_data)


class InstallFlipsBrokenOnDeserializationFailureTest(ModifierLifecycleTestCase):
    def test_install_flips_broken_on_deserialization_failure(self):
        """Assert malformed modifier_data.json rolls back, flips BROKEN, logs LOAD_FAILED."""
        bundle = build_fake_bundle(self.genome_root, 'bad_data')
        # Corrupt the source bundle's modifier_data.json so the copy in
        # runtime is also corrupt — guarantees serializers.deserialize
        # raises during the install's atomic block.
        (bundle / 'modifier_data.json').write_text('not json')

        with self.assertRaises(Exception):
            loader.install_bundle('bad_data')

        modifier = NeuralModifier.objects.get(slug='bad_data')
        self.assertEqual(modifier.status_id, NeuralModifierStatus.BROKEN)
        # Atomic block rolled back; no contribution rows linger.
        self.assertEqual(modifier.contributions.count(), 0)
        # Runtime dir cleaned up by the except branch.
        self.assertFalse((self.runtime_root / 'bad_data').exists())

        log = modifier.current_installation()
        load_failed = log.events.filter(
            event_type_id=NeuralModifierInstallationEventType.LOAD_FAILED
        )
        self.assertEqual(load_failed.count(), 1)
        self.assertIn('traceback', load_failed.first().event_data)


class ReinstallCreatesNewLogTest(ModifierLifecycleTestCase):
    def test_reinstall_creates_new_log(self):
        """Assert reinstall reuses the NeuralModifier row and stacks logs."""
        build_fake_bundle(self.genome_root, 'eta')
        first = loader.install_bundle('eta')
        first_pk = first.pk

        loader.uninstall_bundle('eta')
        second = loader.install_bundle('eta')

        self.assertEqual(second.pk, first_pk)
        log_count = NeuralModifierInstallationLog.objects.filter(
            neural_modifier=second
        ).count()
        # install -> uninstall -> install = 3 logs total.
        self.assertEqual(log_count, 3)
        latest = second.current_installation()
        prior = (
            NeuralModifierInstallationLog.objects.filter(
                neural_modifier=second
            )
            .order_by('-created')[1]
        )
        self.assertGreaterEqual(latest.created, prior.created)


class ListModifiersReportsStatusTest(ModifierLifecycleTestCase):
    def test_list_modifiers_reports_status(self):
        """Assert list_modifiers prints each slug + status."""
        build_fake_bundle(self.genome_root, 'theta')
        build_fake_bundle(self.genome_root, 'iota')
        loader.install_bundle('theta')
        loader.install_bundle('iota')
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
        bundle = build_fake_bundle(self.genome_root, 'bad_semver')
        manifest_path = bundle / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['version'] = 'not-semver'
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

        with self.assertRaisesRegex(ValueError, 'not valid semver'):
            loader.install_bundle('bad_semver')


class InstallRequiresSatisfiedTest(ModifierLifecycleTestCase):
    def test_install_requires_satisfied(self):
        """Assert install proceeds when declared requires are met."""
        build_fake_bundle(self.genome_root, 'base_bundle')
        loader.install_bundle('base_bundle')

        dependent = build_fake_bundle(self.genome_root, 'dep_bundle')
        manifest_path = dependent / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['requires'] = [
            {'slug': 'base_bundle', 'version_spec': '>=0.0.0'}
        ]
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

        loader.install_bundle('dep_bundle')
        self.assertEqual(
            NeuralModifier.objects.get(slug='dep_bundle').status_id,
            NeuralModifierStatus.INSTALLED,
        )


class InstallRequiresMissingTest(ModifierLifecycleTestCase):
    def test_install_requires_missing(self):
        """Assert install refuses when a required bundle is not installed."""
        bundle = build_fake_bundle(self.genome_root, 'lonely')
        manifest_path = bundle / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['requires'] = [
            {'slug': 'ghost_bundle', 'version_spec': '>=1.0.0'}
        ]
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

        with self.assertRaisesRegex(ValueError, 'requires: not satisfied'):
            loader.install_bundle('lonely')


class InstallRequiresVersionMismatchTest(ModifierLifecycleTestCase):
    def test_install_requires_version_mismatch(self):
        """Assert install refuses when a required bundle is the wrong version."""
        build_fake_bundle(self.genome_root, 'old_base')
        loader.install_bundle('old_base')

        dependent = build_fake_bundle(self.genome_root, 'needs_new')
        manifest_path = dependent / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['requires'] = [
            {'slug': 'old_base', 'version_spec': '>=1.0.0'}
        ]
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

        with self.assertRaisesRegex(ValueError, 'requires: not satisfied'):
            loader.install_bundle('needs_new')


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
            self.genome_root, 'evolver', modifier_data=modifier_data_v1
        )
        loader.install_bundle('evolver')

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

        result = loader.upgrade_bundle('evolver')

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
        build_fake_bundle(self.genome_root, 'samever')
        loader.install_bundle('samever')

        with self.assertRaisesRegex(ValueError, 'not newer'):
            loader.upgrade_bundle('samever')

    def test_upgrade_allows_same_version_with_flag(self):
        """Assert --allow-same-version forces the diff to run anyway."""
        build_fake_bundle(self.genome_root, 'samever2')
        loader.install_bundle('samever2')

        result = loader.upgrade_bundle('samever2', allow_same_version=True)
        self.assertEqual(result['previous_version'], result['new_version'])


class BootBundlesSkipsMissingTableTest(ModifierLifecycleTestCase):
    def test_boot_bundles_skips_missing_table(self):
        """Assert boot_bundles returns silently when DB is not ready."""
        from unittest.mock import patch

        from django.db import OperationalError

        # Place a bundle on disk so the function would otherwise try to walk it.
        runtime_bundle = self.runtime_root / 'kappa'
        runtime_bundle.mkdir(parents=True)
        (runtime_bundle / 'manifest.json').write_text('{}')

        target = (
            'neuroplasticity.loader.iter_installed_bundles'
        )
        with patch(target, side_effect=OperationalError('test')):
            # Must not raise.
            loader.boot_bundles()
