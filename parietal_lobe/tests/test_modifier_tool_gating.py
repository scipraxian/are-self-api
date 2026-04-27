"""Tool-set gating by NeuralModifier state.

The per-session Parietal tool manifest filters ToolDefinition rows by
their ``genome`` FK under the tri-state model:

* ``genome=CANONICAL`` — core-shipped tool, always included.
* ``genome=INCUBATOR`` — user-workspace tool, always included.
* ``genome=<bundle>``  — included only when the owning modifier has
  status ``INSTALLED`` (the single live state — ENABLED / DISABLED
  are retired).

Under the genome-FK scheme ownership lives directly on the tool row,
so the filter is a single WHERE clause — no side-car table, no
ContentType, no subquery.
"""

from asgiref.sync import async_to_sync

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
from neuroplasticity.models import NeuralModifier, NeuralModifierStatus
from parietal_lobe.models import ToolDefinition
from parietal_lobe.parietal_lobe import ParietalLobe


class ModifierToolGatingTest(CommonFixturesAPITestCase):
    """Bundle-contributed tools appear only when the bundle is INSTALLED."""

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

        # Core tool: explicit CANONICAL genome — always in the manifest.
        self.core_tool = ToolDefinition.objects.create(
            name='mcp_core_tool',
            description='A core-owned tool.',
            is_async=True,
            genome_id=NeuralModifier.CANONICAL,
        )

        # Bundle tool: genome FK set to an INSTALLED modifier.
        self.modifier = NeuralModifier.objects.create(
            name='Test Bundle',
            slug='test_bundle',
            version='1.0.0',
            author='tests',
            license='MIT',
            manifest_hash='0' * 64,
            manifest_json={},
            status_id=NeuralModifierStatus.INSTALLED,
        )
        self.bundle_tool = ToolDefinition.objects.create(
            name='mcp_bundle_tool',
            description='A bundle-contributed tool.',
            is_async=True,
            genome=self.modifier,
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

    def test_installed_bundle_tool_included(self):
        """INSTALLED: bundle tool appears alongside core tool."""
        self._set_modifier_status(NeuralModifierStatus.INSTALLED)
        names = self._schema_names()
        self.assertIn('mcp_core_tool', names)
        self.assertIn('mcp_bundle_tool', names)

    def test_broken_bundle_tool_excluded(self):
        """BROKEN: bundle tool hidden; core tool still present."""
        self._set_modifier_status(NeuralModifierStatus.BROKEN)
        names = self._schema_names()
        self.assertIn('mcp_core_tool', names)
        self.assertNotIn('mcp_bundle_tool', names)
