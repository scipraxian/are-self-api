"""Tool-set gating by NeuralModifier state (Task 13).

The per-session Parietal tool manifest filters ToolDefinition rows
contributed by a NeuralModifier: only the ENABLED state allows its
tools into the manifest passed to the LLM. Core tools (no
NeuralModifierContribution row) are always included. Disable / broken
/ not-yet-enabled hide the tool until the next session.

See `NEURAL_MODIFIER_COMPLETION_PLAN.md` Task 13.
"""

from asgiref.sync import async_to_sync
from django.contrib.contenttypes.models import ContentType

from central_nervous_system.models import (
    NeuralPathway,
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
)
from common.tests.common_test_case import CommonFixturesAPITestCase
from frontal_lobe.models import ReasoningSession, ReasoningStatusID
from identity.models import IdentityDisc, IdentityType
from neuroplasticity.models import (
    NeuralModifier,
    NeuralModifierContribution,
    NeuralModifierStatus,
)
from parietal_lobe.models import ToolDefinition
from parietal_lobe.parietal_lobe import ParietalLobe


class ModifierToolGatingTest(CommonFixturesAPITestCase):
    """Bundle-contributed tools appear only when the bundle is ENABLED.

    Covers the four non-DISCOVERED lifecycle states (INSTALLED,
    ENABLED, DISABLED, BROKEN). DISCOVERED is not tested: a DISCOVERED
    bundle has no contribution rows yet (the loader has not run), so
    the gating filter has nothing to act on.
    """

    def setUp(self):
        pathway = NeuralPathway.objects.create(name='ToolGating Pathway')
        spike_train = SpikeTrain.objects.create(
            pathway=pathway, status_id=SpikeTrainStatus.RUNNING
        )
        spike = Spike.objects.create(
            spike_train=spike_train,
            status_id=SpikeStatus.RUNNING,
            axoplasm={},
        )
        self.session = ReasoningSession.objects.create(
            spike=spike,
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=10,
            current_focus=5,
            total_xp=0,
        )

        worker_type, _ = IdentityType.objects.get_or_create(
            id=IdentityType.WORKER, defaults={'name': 'Worker'}
        )
        self.identity_disc = IdentityDisc.objects.create(
            name='Tool Gating Disc',
            identity_type=worker_type,
            system_prompt_template='Test',
        )
        self.session.identity_disc = self.identity_disc
        self.session.save(update_fields=['identity_disc'])

        # Core-owned tool: no contribution row ever, regardless of any
        # modifier state below.
        self.core_tool = ToolDefinition.objects.create(
            name='mcp_core_tool',
            description='A core-owned tool.',
            is_async=True,
        )

        # Bundle-owned tool: paired with a NeuralModifierContribution.
        self.bundle_tool = ToolDefinition.objects.create(
            name='mcp_bundle_tool',
            description='A bundle-contributed tool.',
            is_async=True,
        )
        self.modifier = NeuralModifier.objects.create(
            name='Test Bundle',
            slug='test_bundle',
            version='1.0.0',
            author='tests',
            license='MIT',
            manifest_hash='0' * 64,
            manifest_json={},
            status_id=NeuralModifierStatus.ENABLED,
        )
        NeuralModifierContribution.objects.create(
            neural_modifier=self.modifier,
            content_type=ContentType.objects.get_for_model(ToolDefinition),
            object_id=self.bundle_tool.pk,
        )
        self.identity_disc.enabled_tools.add(
            self.core_tool, self.bundle_tool
        )

        self.parietal_lobe = ParietalLobe(self.session, lambda msg: None)

    def _set_modifier_status(self, status_id: int) -> None:
        self.modifier.status_id = status_id
        self.modifier.save(update_fields=['status'])

    def _schema_names(self) -> set:
        schemas = async_to_sync(self.parietal_lobe.build_tool_schemas)()
        return {s['function']['name'] for s in schemas}

    def test_enabled_bundle_tool_included(self):
        """ENABLED: bundle tool appears alongside core tool."""
        self._set_modifier_status(NeuralModifierStatus.ENABLED)
        names = self._schema_names()
        self.assertIn('mcp_core_tool', names)
        self.assertIn('mcp_bundle_tool', names)

    def test_disabled_bundle_tool_excluded(self):
        """DISABLED: bundle tool hidden; core tool still present."""
        self._set_modifier_status(NeuralModifierStatus.DISABLED)
        names = self._schema_names()
        self.assertIn('mcp_core_tool', names)
        self.assertNotIn('mcp_bundle_tool', names)

    def test_broken_bundle_tool_excluded(self):
        """BROKEN: bundle tool hidden; core tool still present."""
        self._set_modifier_status(NeuralModifierStatus.BROKEN)
        names = self._schema_names()
        self.assertIn('mcp_core_tool', names)
        self.assertNotIn('mcp_bundle_tool', names)

    def test_installed_but_not_enabled_excluded(self):
        """INSTALLED: contributions in DB, but tools not yet live.

        The plan is explicit that ENABLED is the only state that
        exposes bundle tools to reasoning. A freshly-INSTALLED bundle
        must be explicitly ENABLED before its tools show up.
        """
        self._set_modifier_status(NeuralModifierStatus.INSTALLED)
        names = self._schema_names()
        self.assertIn('mcp_core_tool', names)
        self.assertNotIn('mcp_bundle_tool', names)

    def test_enable_disable_round_trips_on_next_session(self):
        """ENABLED -> DISABLED -> ENABLED toggles tool visibility.

        Each call to `build_tool_schemas` simulates a new reasoning
        session — no caching layer means state changes land on the
        very next call, which is the contract the lifecycle commands
        rely on.
        """
        self._set_modifier_status(NeuralModifierStatus.ENABLED)
        self.assertIn('mcp_bundle_tool', self._schema_names())

        self._set_modifier_status(NeuralModifierStatus.DISABLED)
        self.assertNotIn('mcp_bundle_tool', self._schema_names())

        self._set_modifier_status(NeuralModifierStatus.ENABLED)
        self.assertIn('mcp_bundle_tool', self._schema_names())
