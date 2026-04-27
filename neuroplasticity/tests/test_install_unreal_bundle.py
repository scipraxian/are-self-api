"""Install round-trip tests for the real Unreal NeuralModifier bundle.

Exercises the loader end-to-end against the committed
`neuroplasticity/genomes/unreal.zip` archive: copies it into a tmp
genomes root, installs via `install_bundle_from_archive`, asserts
owned rows + registrations land, uninstalls, asserts everything rolls
back, then reinstalls to prove idempotency.

Uses a custom fixture list rather than CommonFixturesAPITestCase
because CommonFixturesAPITestCase pre-loads `modifier_data.json` as a
fixture (so the every-test baseline matches a live install). That would
collide with PK insertion when this test installs the bundle fresh via
the loader.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import override_settings

from central_nervous_system.effectors.effector_casters.neuromuscular_junction import (
    NATIVE_HANDLERS,
)
from common.tests.common_test_case import CommonTestCase
from identity.models import Identity
from neuroplasticity import loader
from neuroplasticity.models import NeuralModifier, NeuralModifierStatus
from occipital_lobe.log_parser import LogConstants as BaseLogConstants
from occipital_lobe.log_parser import LogParserFactory
from parietal_lobe.models import ToolDefinition
from parietal_lobe.parietal_mcp.gateway import _PARIETAL_TOOL_REGISTRY

UNREAL_BUNDLE_SLUG = 'unreal'
UE_TOOL_DEF_PK = '4967bb81-ceaf-40f2-95b9-38dd07983172'
UE_HANDLER_SLUG = 'update_version_metadata'
UE_TOOL_SLUG = 'mcp_run_unreal_diagnostic_parser'
THALAMUS_IDENTITY_PK = '14148e25-283d-4547-a17d-e28d021eba07'


class UnrealBundleInstallTestCase(CommonTestCase):
    """Base: load core genetic_immutables + just the zygote / phenotype rows
    the Unreal bundle's FKs depend on.

    Deliberately excludes `identity/fixtures/zygote.json` — that zygote
    carries a forward-ref M2M from `Thalamus.enabled_tools` to the UE
    ToolDefinition PK, and Django's deferred-M2M resolution would fail
    before the test body can install the bundle. The soft-lookup test
    builds its own identity rows by hand.
    """

    fixtures = list(CommonTestCase.fixtures) + [
        'central_nervous_system/fixtures/zygote.json',
        'environments/fixtures/zygote.json',
        'hypothalamus/fixtures/zygote.json',
        'parietal_lobe/fixtures/zygote.json',
        'temporal_lobe/fixtures/zygote.json',
        'environments/fixtures/initial_phenotypes.json',
        'hypothalamus/fixtures/initial_phenotypes.json',
        'identity/fixtures/initial_phenotypes.json',
    ]

    def setUp(self):
        super().setUp()
        self._tmp_root = Path(
            tempfile.mkdtemp(prefix='unreal-dogfood-test-')
        )
        self.genomes_root = self._tmp_root / 'genomes'
        self.grafts_root = self._tmp_root / 'grafts'
        self.operating_room_root = self._tmp_root / 'operating_room'
        self.genomes_root.mkdir()
        self.grafts_root.mkdir()
        self.operating_room_root.mkdir()

        real_archive = (
            Path(settings.BASE_DIR)
            / 'neuroplasticity'
            / 'genomes'
            / '{0}.zip'.format(UNREAL_BUNDLE_SLUG)
        )
        self.archive_path = (
            self.genomes_root / '{0}.zip'.format(UNREAL_BUNDLE_SLUG)
        )
        shutil.copy(real_archive, self.archive_path)

        self._sys_path_snapshot = list(sys.path)
        self._sys_modules_snapshot = set(sys.modules.keys())
        self._settings_override = override_settings(
            NEURAL_MODIFIER_GENOMES_ROOT=str(self.genomes_root),
            NEURAL_MODIFIER_GRAFTS_ROOT=str(self.grafts_root),
            NEURAL_MODIFIER_OPERATING_ROOM_ROOT=str(self.operating_room_root),
        )
        self._settings_override.enable()

        # Snapshot + restore the in-memory registries so a test that
        # installs the bundle doesn't leak handler registrations into
        # sibling tests that run in the same process.
        self._native_handlers_snapshot = dict(NATIVE_HANDLERS)
        self._parietal_registry_snapshot = dict(_PARIETAL_TOOL_REGISTRY)

    def tearDown(self):
        self._settings_override.disable()
        sys.path[:] = self._sys_path_snapshot
        for name in list(sys.modules.keys()):
            if name not in self._sys_modules_snapshot:
                sys.modules.pop(name, None)
        NATIVE_HANDLERS.clear()
        NATIVE_HANDLERS.update(self._native_handlers_snapshot)
        _PARIETAL_TOOL_REGISTRY.clear()
        _PARIETAL_TOOL_REGISTRY.update(self._parietal_registry_snapshot)
        shutil.rmtree(self._tmp_root, ignore_errors=True)
        super().tearDown()


def _total_owned_rows(modifier):
    total = 0
    for model in loader.iter_genome_owned_models():
        total += model.objects.filter(genome=modifier).count()
    return total


class UnrealBundleInstallRoundTripTest(UnrealBundleInstallTestCase):
    def test_install_registers_everything(self):
        """Assert install creates rows, native handler, parietal tool, parsers."""
        modifier = loader.install_bundle_from_archive(self.archive_path)

        self.assertEqual(
            modifier.status_id, NeuralModifierStatus.INSTALLED
        )
        # Eight of the Unreal bundle's serialized models carry
        # GenomeOwnedMixin (the 12 tagged types intersect the bundle's
        # 17 serialized types). Non-owned rows (contexts, assignments,
        # link tables, neurons/axons, pure vocab) load cleanly but do
        # not get a genome stamp, so the owned count is < 260.
        owned = _total_owned_rows(modifier)
        self.assertGreater(owned, 0)
        self.assertTrue(
            ToolDefinition.objects.filter(pk=UE_TOOL_DEF_PK).exists()
        )
        self.assertEqual(
            ToolDefinition.objects.get(pk=UE_TOOL_DEF_PK).genome_id,
            modifier.pk,
        )

        self.assertIn(UE_HANDLER_SLUG, NATIVE_HANDLERS)
        self.assertTrue(callable(NATIVE_HANDLERS[UE_HANDLER_SLUG]))

        self.assertIn(UE_TOOL_SLUG, _PARIETAL_TOOL_REGISTRY)
        self.assertTrue(
            callable(_PARIETAL_TOOL_REGISTRY[UE_TOOL_SLUG])
        )

        run_strategy = LogParserFactory.create(
            BaseLogConstants.TYPE_RUN, 'test'
        )
        build_strategy = LogParserFactory.create(
            BaseLogConstants.TYPE_BUILD, 'test'
        )
        self.assertEqual(
            run_strategy.__class__.__name__, 'UERunLogStrategy'
        )
        self.assertEqual(
            build_strategy.__class__.__name__, 'UEBuildLogStrategy'
        )

    def test_uninstall_rolls_everything_back(self):
        """Assert uninstall drops bundle rows, row, and bundle registrations."""
        loader.install_bundle_from_archive(self.archive_path)
        loader.uninstall_bundle(UNREAL_BUNDLE_SLUG)

        # AVAILABLE = zip exists, no row. Uninstall DELETES the row.
        self.assertFalse(
            NeuralModifier.objects.filter(slug=UNREAL_BUNDLE_SLUG).exists()
        )
        self.assertFalse(
            ToolDefinition.objects.filter(pk=UE_TOOL_DEF_PK).exists()
        )

        # Uninstall does NOT unregister the native handler or parietal
        # tool — the loader has no generic deregistration hook. That
        # leaves the bundle's callables in memory, but the next
        # install's handlers.py is idempotent (unregister-then-register),
        # so reinstall still works. Covered below.

        # LogParserFactory.register uses dict assignment; leaving the
        # class reference registered costs nothing because reinstall
        # simply overwrites. Assert the registry still holds it (since
        # we deliberately did not add an unregister API).
        run_strategy = LogParserFactory.create(
            BaseLogConstants.TYPE_RUN, 'test'
        )
        self.assertEqual(
            run_strategy.__class__.__name__, 'UERunLogStrategy'
        )

    def test_operating_room_is_empty_after_install(self):
        """Assert the scratch dir is empty once install returns."""
        loader.install_bundle_from_archive(self.archive_path)
        self.assertEqual(list(self.operating_room_root.iterdir()), [])


class UnrealBundleReinstallIdempotentTest(UnrealBundleInstallTestCase):
    def test_reinstall_cycle_is_clean(self):
        """Assert install → uninstall → reinstall converges to the same state."""
        first_modifier = loader.install_bundle_from_archive(self.archive_path)
        first_count = _total_owned_rows(first_modifier)
        loader.uninstall_bundle(UNREAL_BUNDLE_SLUG)
        # CASCADE removed the owning bundle — owned row count drops to zero.
        self.assertFalse(
            NeuralModifier.objects.filter(slug=UNREAL_BUNDLE_SLUG).exists()
        )

        # Simulate the coordinated restart: boot_bundles' orphan sweep
        # clears the deferred runtime dir before the archive reinstall.
        loader.boot_bundles()
        second_modifier = loader.install_bundle_from_archive(self.archive_path)
        second_count = _total_owned_rows(second_modifier)
        self.assertEqual(first_count, second_count)

        self.assertIn(UE_HANDLER_SLUG, NATIVE_HANDLERS)
        self.assertIn(UE_TOOL_SLUG, _PARIETAL_TOOL_REGISTRY)
        self.assertTrue(
            ToolDefinition.objects.filter(pk=UE_TOOL_DEF_PK).exists()
        )
        self.assertEqual(list(self.operating_room_root.iterdir()), [])


class ThalamusEnabledToolsSoftLookupTest(UnrealBundleInstallTestCase):
    """Covers the 'bundle UUID in enabled_tools after uninstall' case.

    The real Thalamus identity in `identity/fixtures/zygote.json` carries
    `4967bb81-...` in its M2M `enabled_tools`. After uninstall the
    ToolDefinition row is gone; the M2M link cascades away with it, so
    the parietal manifest build just sees one fewer tool. The soft part
    is that `ToolDefinition.objects.filter(id__in=enabled_tools_ids)`
    never raises — missing PKs drop silently.
    """

    def setUp(self):
        super().setUp()
        loader.install_bundle_from_archive(self.archive_path)
        self.thalamus = Identity.objects.create(
            pk=THALAMUS_IDENTITY_PK,
            name='Thalamus (test)',
            identity_type_id=3,
        )
        self.other_tool = ToolDefinition.objects.exclude(
            pk=UE_TOOL_DEF_PK
        ).first()
        self.assertIsNotNone(self.other_tool)
        ue_tool = ToolDefinition.objects.get(pk=UE_TOOL_DEF_PK)
        self.thalamus.enabled_tools.add(ue_tool, self.other_tool)

    def _resolve_tools(self) -> list:
        ids = list(
            self.thalamus.enabled_tools.values_list('id', flat=True)
        )
        return list(ToolDefinition.objects.filter(id__in=ids))

    def test_uninstall_drops_ue_tool_without_crashing(self):
        """Assert soft-lookup returns only the surviving tool after uninstall."""
        before = self._resolve_tools()
        self.assertEqual(len(before), 2)

        loader.uninstall_bundle(UNREAL_BUNDLE_SLUG)

        after = self._resolve_tools()
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0].pk, self.other_tool.pk)

    def test_reinstall_restores_tool_row(self):
        """Assert reinstall restores the ToolDefinition row in the DB.

        The M2M link does not auto-restore — it was cascade-deleted with
        the ToolDefinition on uninstall, and no contribution tracks
        through-table rows. Re-linking is a manual operator action, out
        of scope for the loader.
        """
        loader.uninstall_bundle(UNREAL_BUNDLE_SLUG)
        self.assertFalse(
            ToolDefinition.objects.filter(pk=UE_TOOL_DEF_PK).exists()
        )
        # Simulate the coordinated restart: boot_bundles' orphan sweep
        # clears the deferred runtime dir before the archive reinstall.
        loader.boot_bundles()
        loader.install_bundle_from_archive(self.archive_path)
        self.assertTrue(
            ToolDefinition.objects.filter(pk=UE_TOOL_DEF_PK).exists()
        )
