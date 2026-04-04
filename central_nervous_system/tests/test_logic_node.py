from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync

from central_nervous_system.effectors.effector_casters.pathway_logic_node import (
    BB_LOOP_COUNT,
    MODE_GATE,
    MODE_RETRY,
    MODE_WAIT,
    OP_EQUALS,
    OP_EXISTS,
    OP_GT,
    OP_NOT_EQUALS,
    pathway_logic_node,
)
from central_nervous_system.models import (
    Effector,
    NeuralPathway,
    Neuron,
    NeuronContext,
    Spike,
    SpikeTrain,
    SpikeStatus,
)
from common.tests.common_test_case import CommonFixturesAPITestCase
from environments.models import (
    Executable,
    ProjectEnvironment,
    ProjectEnvironmentStatus,
    ProjectEnvironmentType,
)


class LogicNodeTestBase(CommonFixturesAPITestCase):
    """Shared setup for logic node tests."""

    def setUp(self):
        super().setUp()
        env_type = ProjectEnvironmentType.objects.get_or_create(name='Test')[0]
        env_status = ProjectEnvironmentStatus.objects.get_or_create(name='Ready')[0]
        self.env = ProjectEnvironment.objects.create(
            name='Test Env', type=env_type, status=env_status, selected=True
        )

        self.exe = Executable.objects.create(
            name='LogicExe', executable='pathway_logic_neuron', internal=True
        )
        self.effector = Effector.objects.create(name='LogicNode', executable=self.exe)
        self.pathway = NeuralPathway.objects.create(name='Test Pathway')
        self.neuron = Neuron.objects.create(
            pathway=self.pathway,
            effector=self.effector,
            environment=self.env,
            is_root=True,
        )
        self.train = SpikeTrain.objects.create(
            pathway=self.pathway,
            environment=self.env,
            status_id=SpikeStatus.RUNNING,
        )

    def _make_spike(self, blackboard=None, provenance=None):
        """Create a spike on the test neuron."""
        return Spike.objects.create(
            spike_train=self.train,
            neuron=self.neuron,
            effector=self.effector,
            status_id=SpikeStatus.RUNNING,
            blackboard=blackboard or {},
            provenance=provenance,
        )

    def _set_context(self, **kwargs):
        """Set NeuronContext key-value pairs on the test neuron."""
        for key, value in kwargs.items():
            NeuronContext.objects.create(
                neuron=self.neuron, key=key, value=str(value)
            )

    def _run(self, spike):
        """Run the logic node synchronously."""
        return async_to_sync(pathway_logic_node)(str(spike.id))


class RetryModeTest(LogicNodeTestBase):
    """Assert retry mode counts via blackboard, not provenance walking."""

    def test_first_iteration_returns_success(self):
        """Assert first retry attempt returns 200 (LOOPING)."""
        self._set_context(logic_mode=MODE_RETRY, max_retries=3)
        spike = self._make_spike(blackboard={})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('LOOPING', msg)
        self.assertIn('attempt 1 of 4', msg)

    def test_writes_loop_count_to_blackboard(self):
        """Assert retry mode writes loop_count to the blackboard."""
        self._set_context(logic_mode=MODE_RETRY, max_retries=3)
        spike = self._make_spike(blackboard={})

        self._run(spike)
        spike.refresh_from_db()

        self.assertEqual(spike.blackboard[BB_LOOP_COUNT], 1)

    def test_mid_loop_continues(self):
        """Assert loop continues when count is under max_retries."""
        self._set_context(logic_mode=MODE_RETRY, max_retries=3)
        spike = self._make_spike(blackboard={BB_LOOP_COUNT: 1})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('attempt 2 of 4', msg)
        spike.refresh_from_db()
        self.assertEqual(spike.blackboard[BB_LOOP_COUNT], 2)

    def test_limit_reached_returns_failure(self):
        """Assert retry returns 500 when loop_count reaches max_retries."""
        self._set_context(logic_mode=MODE_RETRY, max_retries=3)
        spike = self._make_spike(blackboard={BB_LOOP_COUNT: 3})

        code, msg = self._run(spike)

        self.assertEqual(code, 500)
        self.assertIn('LIMIT REACHED', msg)

    def test_zero_retries_passes_through(self):
        """Assert max_retries=0 is a pass-through."""
        self._set_context(logic_mode=MODE_RETRY, max_retries=0)
        spike = self._make_spike()

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('pass-through', msg)

    def test_no_config_defaults_to_retry_passthrough(self):
        """Assert no NeuronContext defaults to retry mode with 0 retries."""
        spike = self._make_spike()

        code, msg = self._run(spike)

        self.assertEqual(code, 200)


class GateModeTest(LogicNodeTestBase):
    """Assert gate mode checks blackboard keys against conditions."""

    def test_exists_passes_when_key_present(self):
        """Assert gate passes when key exists in blackboard."""
        self._set_context(logic_mode=MODE_GATE, gate_key='task_type', gate_operator=OP_EXISTS)
        spike = self._make_spike(blackboard={'task_type': 'art'})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('PASS', msg)

    def test_exists_fails_when_key_missing(self):
        """Assert gate fails when key is not in blackboard."""
        self._set_context(logic_mode=MODE_GATE, gate_key='task_type', gate_operator=OP_EXISTS)
        spike = self._make_spike(blackboard={})

        code, msg = self._run(spike)

        self.assertEqual(code, 500)
        self.assertIn('FAIL', msg)

    def test_equals_passes_on_match(self):
        """Assert gate passes when blackboard value equals expected."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='task_type',
            gate_operator=OP_EQUALS, gate_value='art'
        )
        spike = self._make_spike(blackboard={'task_type': 'art'})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)

    def test_equals_fails_on_mismatch(self):
        """Assert gate fails when blackboard value does not equal expected."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='task_type',
            gate_operator=OP_EQUALS, gate_value='art'
        )
        spike = self._make_spike(blackboard={'task_type': 'code'})

        code, msg = self._run(spike)

        self.assertEqual(code, 500)

    def test_not_equals_passes_on_mismatch(self):
        """Assert gate passes when blackboard value differs from expected."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='task_type',
            gate_operator=OP_NOT_EQUALS, gate_value='art'
        )
        spike = self._make_spike(blackboard={'task_type': 'code'})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)

    def test_gt_passes_when_greater(self):
        """Assert gate passes on numeric greater-than comparison."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='score',
            gate_operator=OP_GT, gate_value='50'
        )
        spike = self._make_spike(blackboard={'score': '75'})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)

    def test_gt_fails_when_equal(self):
        """Assert gate fails when value equals threshold (not strictly greater)."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='score',
            gate_operator=OP_GT, gate_value='50'
        )
        spike = self._make_spike(blackboard={'score': '50'})

        code, msg = self._run(spike)

        self.assertEqual(code, 500)

    def test_no_gate_key_returns_failure(self):
        """Assert gate mode with no gate_key configured returns 500."""
        self._set_context(logic_mode=MODE_GATE)
        spike = self._make_spike(blackboard={'anything': 'here'})

        code, msg = self._run(spike)

        self.assertEqual(code, 500)
        self.assertIn('no gate_key', msg)


class WaitModeTest(LogicNodeTestBase):
    """Assert wait mode delays and always passes."""

    @patch(
        'central_nervous_system.effectors.effector_casters.pathway_logic_node.asyncio.sleep',
        new_callable=AsyncMock,
    )
    def test_wait_with_delay(self, mock_sleep):
        """Assert wait mode sleeps for configured duration."""
        self._set_context(logic_mode=MODE_WAIT, delay=5)
        spike = self._make_spike()

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('5s', msg)
        mock_sleep.assert_called_once_with(5)

    def test_wait_no_delay_passes_through(self):
        """Assert wait mode with no delay is a pass-through."""
        self._set_context(logic_mode=MODE_WAIT)
        spike = self._make_spike()

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('pass-through', msg)


class UnknownModeTest(LogicNodeTestBase):
    """Assert unknown modes pass through safely."""

    def test_unknown_mode_returns_200(self):
        """Assert unknown logic_mode returns 200 with a warning."""
        self._set_context(logic_mode='bogus')
        spike = self._make_spike()

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('bogus', msg)
