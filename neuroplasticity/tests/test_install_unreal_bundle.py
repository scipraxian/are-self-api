"""Install round-trip tests for an unreal-shaped NeuralModifier bundle.

Exercises the loader end-to-end against a *synthetic* archive built on
the fly during ``setUp`` — slug, ToolDefinition PK, native-handler
slug, parietal-tool slug, and parser class names all match what the
real ``neuroplasticity/genomes/unreal.zip`` exposes, but no
production artifact is touched. The test owns its bundle.

Uses a custom fixture list rather than CommonFixturesAPITestCase
because CommonFixturesAPITestCase pre-loads `modifier_data.json` as a
fixture (so the every-test baseline matches a live install). That would
collide with PK insertion when this test installs the bundle fresh via
the loader.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path

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

# Entry module name for the synthetic bundle. Distinct from the real
# unreal bundle's `are_self_unreal` so a stray production artifact
# can't shadow this fixture by name.
SYNTH_ENTRY_MODULE = 'are_self_unreal_synthetic_test'

# Source for the synthetic entry module's __init__.py. Registers the
# same names + class shapes the real unreal bundle exposes so the
# test assertions remain meaningful. Idempotent — re-import on
# reinstall must succeed without duplicate-registration errors.
_SYNTH_ENTRY_INIT_PY = '''\
"""Synthetic test stand-in for the unreal bundle's entry module.

Registers the names and class shapes test_install_unreal_bundle.py
asserts against, so the test does not depend on the committed
neuroplasticity/genomes/unreal.zip artifact. Pop-then-register makes
re-import on a reinstall idempotent.
"""

from central_nervous_system.effectors.effector_casters.neuromuscular_junction import (  # noqa: E501
    NATIVE_HANDLERS,
    register_native_handler,
)
from occipital_lobe.log_parser import (
    LogConstants,
    LogParserFactory,
    LogParserStrategy,
)
from parietal_lobe.parietal_mcp.gateway import (
    _PARIETAL_TOOL_REGISTRY,
    register_parietal_tool,
)


class UERunLogStrategy(LogParserStrategy):
    """Synthetic stand-in. Class name matches what the test asserts."""

    def parse_chunk(self, lines):
        return []


class UEBuildLogStrategy(LogParserStrategy):
    """Synthetic stand-in. Class name matches what the test asserts."""

    def parse_chunk(self, lines):
        return []


def update_version_metadata(*args, **kwargs):
    """Synthetic native handler stand-in."""
    return None


async def mcp_run_unreal_diagnostic_parser(*args, **kwargs):
    """Synthetic parietal tool stand-in."""
    return ''


NATIVE_HANDLERS.pop('update_version_metadata', None)
register_native_handler('update_version_metadata', update_version_metadata)

_PARIETAL_TOOL_REGISTRY.pop('mcp_run_unreal_diagnostic_parser', None)
register_parietal_tool(
    'mcp_run_unreal_diagnostic_parser',
    mcp_run_unreal_diagnostic_parser,
)

LogParserFactory.register(LogConstants.TYPE_RUN, UERunLogStrategy)
LogParserFactory.register(LogConstants.TYPE_BUILD, UEBuildLogStrategy)
'''


def _build_synthetic_unreal_archive(
    archive_path: Path, scratch_dir: Path
) -> Path:
    """Build a synthetic unreal-shaped bundle archive entirely in tmp.

    The output zip contains:

      * ``manifest.json`` declaring slug ``'unreal'`` and our synthetic
        entry module.
      * ``modifier_data.json`` with a single ``ToolDefinition`` row at
        ``UE_TOOL_DEF_PK`` — the only owned-row PK the suite asserts on.
      * ``code/<entry_module>/__init__.py`` registering the native
        handler, parietal tool, and parser strategies whose names match
        the test assertions.

    Mirrors the real unreal bundle's *contract* (names + class shapes +
    one ToolDefinition PK) without copying its production artifact.
    """
    scratch_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = scratch_dir / UNREAL_BUNDLE_SLUG
    bundle_dir.mkdir()

    manifest = {
        'slug': UNREAL_BUNDLE_SLUG,
        'name': 'Synthetic Unreal Test Bundle',
        'version': '0.0.1',
        'genome': str(uuid.uuid4()),
        'author': 'tests',
        'license': 'MIT',
        'description': 'Synthetic test fixture; no production artifact.',
        'entry_modules': [SYNTH_ENTRY_MODULE],
    }
    (bundle_dir / 'manifest.json').write_text(
        json.dumps(manifest, indent=2) + '\n'
    )

    # ``ToolDefinition`` carries ``DefaultFieldsMixin`` (created /
    # modified) — these are non-nullable and ``auto_now_add`` /
    # ``auto_now`` do not fire through ``serializers.deserialize``,
    # so explicit timestamps are required in the payload.
    fixed_ts = '2026-01-01T00:00:00Z'
    modifier_data = [
        {
            'model': 'parietal_lobe.tooldefinition',
            'pk': UE_TOOL_DEF_PK,
            'fields': {
                'created': fixed_ts,
                'modified': fixed_ts,
                'name': UE_TOOL_SLUG,
                'description': 'Synthetic UE diagnostic parser tool.',
                'is_async': True,
            },
        }
    ]
    (bundle_dir / 'modifier_data.json').write_text(
        json.dumps(modifier_data, indent=2) + '\n'
    )

    code_dir = bundle_dir / 'code'
    code_dir.mkdir()
    pkg_dir = code_dir / SYNTH_ENTRY_MODULE
    pkg_dir.mkdir()
    (pkg_dir / '__init__.py').write_text(_SYNTH_ENTRY_INIT_PY)

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(bundle_dir.rglob('*')):
            if path.is_dir():
                continue
            arcname = Path(UNREAL_BUNDLE_SLUG) / path.relative_to(bundle_dir)
            zf.write(path, arcname.as_posix())

    return archive_path


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

        # Build a synthetic unreal-shaped archive on the fly so this
        # test never reads or copies the committed production
        # neuroplasticity/genomes/unreal.zip.
        self.archive_path = (
            self.genomes_root / '{0}.zip'.format(UNREAL_BUNDLE_SLUG)
        )
        _build_synthetic_unreal_archive(
            self.archive_path, self._tmp_root / 'scratch'
        )

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
        # sibling tests that run in the same process. The synthetic
        # bundle's __init__.py re-registers TYPE_BUILD/TYPE_RUN log
        # parser strategies under the same keys the real unreal bundle
        # uses, overwriting them with stubs whose parse_chunk returns
        # []. Without restoring LogParserFactory._registry, any later
        # bundle parser test that calls LogParserFactory.create()
        # picks up the stub and fails with IndexError.
        self._native_handlers_snapshot = dict(NATIVE_HANDLERS)
        self._parietal_registry_snapshot = dict(_PARIETAL_TOOL_REGISTRY)
        self._log_parser_registry_snapshot = dict(
            LogParserFactory._registry
        )

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
        LogParserFactory._registry.clear()
        LogParserFactory._registry.update(self._log_parser_registry_snapshot)
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
