"""FK-softening test: ToolCall.tool cascades on bundle uninstall.

ToolCall is transactional — its arguments JSON is shaped against a
specific ToolDefinition schema, so orphaning rows after the tool is
gone has no forensic value. Softened from PROTECT to CASCADE so
``modifier.delete()`` does not raise ProtectedError when the bundle
owns the tool and real turns have fired against it.
"""

from central_nervous_system.models import (
    NeuralPathway,
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
)
from common.tests.common_test_case import CommonFixturesAPITestCase
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)
from neuroplasticity import loader
from neuroplasticity.models import NeuralModifier, NeuralModifierStatus
from parietal_lobe.models import ToolCall, ToolDefinition


class ToolCallCascadesOnToolDeleteTest(CommonFixturesAPITestCase):

    def setUp(self):
        super().setUp()
        self.modifier = NeuralModifier.objects.create(
            name='FK Test Bundle',
            slug='fk-test-toolcall-cascade',
            version='1.0.0',
            author='tests',
            license='MIT',
            manifest_hash='0' * 64,
            manifest_json={},
            status_id=NeuralModifierStatus.INSTALLED,
        )
        self.bundle_tool = ToolDefinition.objects.create(
            name='mcp_bundle_tool_for_cascade',
            description='Tool contributed by a bundle.',
            is_async=True,
            genome=self.modifier,
        )

        pathway = NeuralPathway.objects.create(name='Cascade Pathway')
        spike_train = SpikeTrain.objects.create(
            pathway=pathway, status_id=SpikeTrainStatus.RUNNING
        )
        spike = Spike.objects.create(
            spike_train=spike_train,
            status_id=SpikeStatus.RUNNING,
            axoplasm={},
        )
        session = ReasoningSession.objects.create(
            spike=spike,
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=10,
        )
        self.turn = ReasoningTurn.objects.create(
            session=session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )
        self.tool_call = ToolCall.objects.create(
            turn=self.turn,
            tool=self.bundle_tool,
            arguments='{}',
        )

    def test_uninstall_cascades_tool_call_rows(self):
        """Assert ToolCall rows cascade away when the owning bundle uninstalls."""
        self.assertTrue(
            ToolCall.objects.filter(pk=self.tool_call.pk).exists()
        )

        loader.uninstall_bundle(self.modifier.slug)

        self.assertFalse(
            ToolDefinition.objects.filter(pk=self.bundle_tool.pk).exists()
        )
        self.assertFalse(
            ToolCall.objects.filter(pk=self.tool_call.pk).exists()
        )
        # The enclosing turn survives — only its ToolCall rows went.
        self.assertTrue(
            ReasoningTurn.objects.filter(pk=self.turn.pk).exists()
        )
