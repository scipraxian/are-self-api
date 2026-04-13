from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync

from central_nervous_system.effectors.effector_casters.pathway_logic_node import (
    BB_LOOP_COUNT,
    CTX_DELAY,
    CTX_GATE_KEY,
    CTX_GATE_OPERATOR,
    CTX_GATE_VALUE,
    CTX_LOGIC_MODE,
    CTX_MAX_RETRIES,
    CTX_RETRY_DELAY,
    MODE_GATE,
    MODE_RETRY,
    MODE_WAIT,
    OP_EQUALS,
    OP_EXISTS,
    OP_GT,
    OP_LT,
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

    def _make_spike(self, axoplasm=None, provenance=None):
        """Create a spike on the test neuron."""
        return Spike.objects.create(
            spike_train=self.train,
            neuron=self.neuron,
            effector=self.effector,
            status_id=SpikeStatus.RUNNING,
            axoplasm=axoplasm or {},
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


# ── Retry Mode ──────────────────────────────────────────────


class RetryModeTest(LogicNodeTestBase):
    """Assert retry mode counts via axoplasm, not provenance walking."""

    def test_first_iteration_returns_success(self):
        """Assert first retry attempt returns 200 (LOOPING)."""
        self._set_context(logic_mode=MODE_RETRY, max_retries=3)
        spike = self._make_spike(axoplasm={})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('LOOPING', msg)
        self.assertIn('attempt 1 of 4', msg)

    def test_writes_loop_count_to_axoplasm(self):
        """Assert retry mode writes loop_count to the axoplasm."""
        self._set_context(logic_mode=MODE_RETRY, max_retries=3)
        spike = self._make_spike(axoplasm={})

        self._run(spike)
        spike.refresh_from_db()

        self.assertEqual(spike.axoplasm[BB_LOOP_COUNT], 1)

    def test_mid_loop_continues(self):
        """Assert loop continues when count is under max_retries."""
        self._set_context(logic_mode=MODE_RETRY, max_retries=3)
        spike = self._make_spike(axoplasm={BB_LOOP_COUNT: 1})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('attempt 2 of 4', msg)
        spike.refresh_from_db()
        self.assertEqual(spike.axoplasm[BB_LOOP_COUNT], 2)

    def test_limit_reached_returns_failure(self):
        """Assert retry returns 500 when loop_count reaches max_retries."""
        self._set_context(logic_mode=MODE_RETRY, max_retries=3)
        spike = self._make_spike(axoplasm={BB_LOOP_COUNT: 3})

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

    def test_single_retry_loops_then_stops(self):
        """Assert max_retries=1 loops once then hits limit."""
        self._set_context(logic_mode=MODE_RETRY, max_retries=1)
        spike = self._make_spike(axoplasm={})

        # First pass: loop_count 0 < 1, LOOPING
        code, msg = self._run(spike)
        self.assertEqual(code, 200)
        self.assertIn('LOOPING', msg)

        spike.refresh_from_db()
        self.assertEqual(spike.axoplasm[BB_LOOP_COUNT], 1)

        # Second pass: loop_count 1 >= 1, LIMIT REACHED
        code, msg = self._run(spike)
        self.assertEqual(code, 500)
        self.assertIn('LIMIT REACHED', msg)

    def test_blackboard_preserves_other_keys(self):
        """Assert retry mode only touches loop_count, leaves other axoplasm keys."""
        self._set_context(logic_mode=MODE_RETRY, max_retries=3)
        spike = self._make_spike(axoplasm={'task_type': 'art', 'score': '95'})

        self._run(spike)
        spike.refresh_from_db()

        self.assertEqual(spike.axoplasm['task_type'], 'art')
        self.assertEqual(spike.axoplasm['score'], '95')
        self.assertEqual(spike.axoplasm[BB_LOOP_COUNT], 1)

    def test_negative_max_retries_passes_through(self):
        """Assert negative max_retries value is treated as pass-through."""
        self._set_context(logic_mode=MODE_RETRY, max_retries=-1)
        spike = self._make_spike()

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('pass-through', msg)

    def test_non_numeric_max_retries_passes_through(self):
        """Assert non-numeric max_retries is treated as 0 (pass-through)."""
        self._set_context(logic_mode=MODE_RETRY, max_retries='abc')
        spike = self._make_spike()

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('pass-through', msg)

    def test_loop_count_starts_at_zero_when_missing(self):
        """Assert missing loop_count in axoplasm is treated as 0."""
        self._set_context(logic_mode=MODE_RETRY, max_retries=2)
        spike = self._make_spike(axoplasm={'some_other_key': 'value'})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('attempt 1 of 3', msg)
        spike.refresh_from_db()
        self.assertEqual(spike.axoplasm[BB_LOOP_COUNT], 1)

    def test_limit_does_not_write_blackboard(self):
        """Assert axoplasm is not written when limit is reached."""
        self._set_context(logic_mode=MODE_RETRY, max_retries=2)
        spike = self._make_spike(axoplasm={BB_LOOP_COUNT: 2})

        code, _msg = self._run(spike)

        self.assertEqual(code, 500)
        spike.refresh_from_db()
        # loop_count stays at 2, not incremented
        self.assertEqual(spike.axoplasm[BB_LOOP_COUNT], 2)


# ── Retry Delay (backward compat: retry_delay vs delay) ─────


class RetryDelayTest(LogicNodeTestBase):
    """Assert retry mode uses 'retry_delay' for inter-attempt sleep."""

    @patch(
        'central_nervous_system.effectors.effector_casters'
        '.pathway_logic_node.asyncio.sleep',
        new_callable=AsyncMock,
    )
    def test_retry_delay_key_is_read(self, mock_sleep):
        """Assert 'retry_delay' context key triggers sleep."""
        self._set_context(logic_mode=MODE_RETRY, max_retries=3, retry_delay=2)
        spike = self._make_spike(axoplasm={})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        mock_sleep.assert_called_once_with(2)

    @patch(
        'central_nervous_system.effectors.effector_casters'
        '.pathway_logic_node.asyncio.sleep',
        new_callable=AsyncMock,
    )
    def test_no_retry_delay_no_sleep(self, mock_sleep):
        """Assert no sleep when retry_delay is not set."""
        self._set_context(logic_mode=MODE_RETRY, max_retries=3)
        spike = self._make_spike(axoplasm={})

        self._run(spike)

        mock_sleep.assert_not_called()

    @patch(
        'central_nervous_system.effectors.effector_casters'
        '.pathway_logic_node.asyncio.sleep',
        new_callable=AsyncMock,
    )
    def test_delay_key_is_NOT_used_for_retry(self, mock_sleep):
        """Assert 'delay' key does NOT trigger sleep in retry mode.

        Retry uses 'retry_delay'. 'delay' is for wait mode only.
        This test would have caught the frontend/backend key mismatch.
        """
        self._set_context(logic_mode=MODE_RETRY, max_retries=3, delay=99)
        spike = self._make_spike(axoplasm={})

        self._run(spike)

        mock_sleep.assert_not_called()


# ── Gate Mode ────────────────────────────────────────────────


class GateModeTest(LogicNodeTestBase):
    """Assert gate mode checks axoplasm keys against conditions."""

    def test_exists_passes_when_key_present(self):
        """Assert gate passes when key exists in axoplasm."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='task_type',
            gate_operator=OP_EXISTS,
        )
        spike = self._make_spike(axoplasm={'task_type': 'art'})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('PASS', msg)

    def test_exists_fails_when_key_missing(self):
        """Assert gate fails when key is not in axoplasm."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='task_type',
            gate_operator=OP_EXISTS,
        )
        spike = self._make_spike(axoplasm={})

        code, msg = self._run(spike)

        self.assertEqual(code, 500)
        self.assertIn('FAIL', msg)

    def test_exists_passes_when_value_is_empty_string(self):
        """Assert gate EXISTS passes even if value is empty string."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='task_type',
            gate_operator=OP_EXISTS,
        )
        spike = self._make_spike(axoplasm={'task_type': ''})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('PASS', msg)

    def test_exists_passes_when_value_is_zero(self):
        """Assert gate EXISTS passes when value is numeric 0."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='count',
            gate_operator=OP_EXISTS,
        )
        spike = self._make_spike(axoplasm={'count': 0})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('PASS', msg)

    def test_equals_passes_on_match(self):
        """Assert gate passes when axoplasm value equals expected."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='task_type',
            gate_operator=OP_EQUALS, gate_value='art',
        )
        spike = self._make_spike(axoplasm={'task_type': 'art'})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)

    def test_equals_fails_on_mismatch(self):
        """Assert gate fails when axoplasm value does not equal expected."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='task_type',
            gate_operator=OP_EQUALS, gate_value='art',
        )
        spike = self._make_spike(axoplasm={'task_type': 'code'})

        code, msg = self._run(spike)

        self.assertEqual(code, 500)

    def test_not_equals_passes_on_mismatch(self):
        """Assert gate passes when axoplasm value differs from expected."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='task_type',
            gate_operator=OP_NOT_EQUALS, gate_value='art',
        )
        spike = self._make_spike(axoplasm={'task_type': 'code'})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)

    def test_not_equals_fails_on_match(self):
        """Assert gate NOT_EQUALS fails when values are equal."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='task_type',
            gate_operator=OP_NOT_EQUALS, gate_value='art',
        )
        spike = self._make_spike(axoplasm={'task_type': 'art'})

        code, msg = self._run(spike)

        self.assertEqual(code, 500)

    def test_gt_passes_when_greater(self):
        """Assert gate passes on numeric greater-than comparison."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='score',
            gate_operator=OP_GT, gate_value='50',
        )
        spike = self._make_spike(axoplasm={'score': '75'})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)

    def test_gt_fails_when_equal(self):
        """Assert gate fails when value equals threshold (not strictly >)."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='score',
            gate_operator=OP_GT, gate_value='50',
        )
        spike = self._make_spike(axoplasm={'score': '50'})

        code, msg = self._run(spike)

        self.assertEqual(code, 500)

    def test_gt_fails_when_less(self):
        """Assert gate GT fails when axoplasm value is less."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='score',
            gate_operator=OP_GT, gate_value='50',
        )
        spike = self._make_spike(axoplasm={'score': '25'})

        code, msg = self._run(spike)

        self.assertEqual(code, 500)

    def test_lt_passes_when_less(self):
        """Assert gate passes on numeric less-than comparison."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='score',
            gate_operator=OP_LT, gate_value='50',
        )
        spike = self._make_spike(axoplasm={'score': '25'})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)

    def test_lt_fails_when_equal(self):
        """Assert gate LT fails when values are equal."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='score',
            gate_operator=OP_LT, gate_value='50',
        )
        spike = self._make_spike(axoplasm={'score': '50'})

        code, msg = self._run(spike)

        self.assertEqual(code, 500)

    def test_lt_fails_when_greater(self):
        """Assert gate LT fails when axoplasm value is greater."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='score',
            gate_operator=OP_LT, gate_value='50',
        )
        spike = self._make_spike(axoplasm={'score': '75'})

        code, msg = self._run(spike)

        self.assertEqual(code, 500)

    def test_no_gate_key_returns_failure(self):
        """Assert gate mode with no gate_key configured returns 500."""
        self._set_context(logic_mode=MODE_GATE)
        spike = self._make_spike(axoplasm={'anything': 'here'})

        code, msg = self._run(spike)

        self.assertEqual(code, 500)
        self.assertIn('no gate_key', msg)

    def test_unknown_operator_returns_failure(self):
        """Assert unknown gate operator returns 500."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='score',
            gate_operator='contains', gate_value='foo',
        )
        spike = self._make_spike(axoplasm={'score': 'foobar'})

        code, msg = self._run(spike)

        self.assertEqual(code, 500)
        self.assertIn('unknown operator', msg)

    def test_numeric_comparison_with_non_numeric_value(self):
        """Assert GT with non-numeric axoplasm value returns FAIL (0.0 > N)."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='score',
            gate_operator=OP_GT, gate_value='50',
        )
        spike = self._make_spike(axoplasm={'score': 'not_a_number'})

        code, msg = self._run(spike)

        # _safe_float('not_a_number') -> 0.0; 0.0 > 50.0 -> FAIL
        self.assertEqual(code, 500)

    def test_gate_missing_key_with_non_exists_operator(self):
        """Assert non-EXISTS operator fails when key is missing entirely."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='missing_key',
            gate_operator=OP_EQUALS, gate_value='something',
        )
        spike = self._make_spike(axoplasm={})

        code, msg = self._run(spike)

        self.assertEqual(code, 500)
        self.assertIn('not found', msg)

    def test_equals_with_whitespace_value(self):
        """Assert equals strips and compares correctly."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='name',
            gate_operator=OP_EQUALS, gate_value='hello',
        )
        # Axoplasm has value with trailing whitespace
        spike = self._make_spike(axoplasm={'name': ' hello '})

        code, msg = self._run(spike)

        # str(bb_raw).strip() -> 'hello' == 'hello' -> PASS
        self.assertEqual(code, 200)

    def test_gate_with_empty_blackboard(self):
        """Assert gate handles spike with empty axoplasm gracefully."""
        self._set_context(
            logic_mode=MODE_GATE, gate_key='key',
            gate_operator=OP_EXISTS,
        )
        spike = self._make_spike(axoplasm={})

        code, msg = self._run(spike)

        self.assertEqual(code, 500)
        self.assertIn('not found', msg)


# ── Wait Mode ────────────────────────────────────────────────


class WaitModeTest(LogicNodeTestBase):
    """Assert wait mode delays and always passes."""

    @patch(
        'central_nervous_system.effectors.effector_casters'
        '.pathway_logic_node.asyncio.sleep',
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

    @patch(
        'central_nervous_system.effectors.effector_casters'
        '.pathway_logic_node.asyncio.sleep',
        new_callable=AsyncMock,
    )
    def test_wait_with_large_delay(self, mock_sleep):
        """Assert wait mode handles large delay values."""
        self._set_context(logic_mode=MODE_WAIT, delay=300)
        spike = self._make_spike()

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('300s', msg)
        mock_sleep.assert_called_once_with(300)

    def test_wait_non_numeric_delay_passes_through(self):
        """Assert non-numeric delay is treated as 0 (pass-through)."""
        self._set_context(logic_mode=MODE_WAIT, delay='abc')
        spike = self._make_spike()

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('pass-through', msg)


# ── Unknown Mode ─────────────────────────────────────────────


class UnknownModeTest(LogicNodeTestBase):
    """Assert unknown modes pass through safely."""

    def test_unknown_mode_returns_200(self):
        """Assert unknown logic_mode returns 200 with a warning."""
        self._set_context(logic_mode='bogus')
        spike = self._make_spike()

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('bogus', msg)

    def test_mode_is_case_insensitive(self):
        """Assert mode matching is case-insensitive."""
        self._set_context(logic_mode='RETRY', max_retries=2)
        spike = self._make_spike(axoplasm={})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('LOOPING', msg)

    def test_mode_with_whitespace_is_trimmed(self):
        """Assert whitespace around mode value is stripped."""
        self._set_context(logic_mode='  gate  ', gate_key='k', gate_operator=OP_EXISTS)
        spike = self._make_spike(axoplasm={'k': 'v'})

        code, msg = self._run(spike)

        self.assertEqual(code, 200)
        self.assertIn('PASS', msg)


# ── Context Key Constants ────────────────────────────────────


class ContextKeyConstantsTest(LogicNodeTestBase):
    """Assert context key constants match expected values.

    These tests would have caught the retry_delay vs delay mismatch
    between frontend and backend.
    """

    def test_ctx_delay_value(self):
        """Assert CTX_DELAY constant is 'delay' (used by wait mode)."""
        self.assertEqual(CTX_DELAY, 'delay')

    def test_ctx_retry_delay_value(self):
        """Assert CTX_RETRY_DELAY constant is 'retry_delay'."""
        self.assertEqual(CTX_RETRY_DELAY, 'retry_delay')

    def test_ctx_max_retries_value(self):
        """Assert CTX_MAX_RETRIES constant is 'max_retries'."""
        self.assertEqual(CTX_MAX_RETRIES, 'max_retries')

    def test_ctx_logic_mode_value(self):
        """Assert CTX_LOGIC_MODE constant is 'logic_mode'."""
        self.assertEqual(CTX_LOGIC_MODE, 'logic_mode')

    def test_ctx_gate_key_value(self):
        """Assert CTX_GATE_KEY constant is 'gate_key'."""
        self.assertEqual(CTX_GATE_KEY, 'gate_key')

    def test_ctx_gate_operator_value(self):
        """Assert CTX_GATE_OPERATOR constant is 'gate_operator'."""
        self.assertEqual(CTX_GATE_OPERATOR, 'gate_operator')

    def test_ctx_gate_value_value(self):
        """Assert CTX_GATE_VALUE constant is 'gate_value'."""
        self.assertEqual(CTX_GATE_VALUE, 'gate_value')

    def test_bb_loop_count_value(self):
        """Assert BB_LOOP_COUNT constant is 'loop_count'."""
        self.assertEqual(BB_LOOP_COUNT, 'loop_count')


# ── Full Retry Lifecycle ─────────────────────────────────────


class RetryLifecycleTest(LogicNodeTestBase):
    """Assert the complete retry loop lifecycle from start to limit."""

    def test_full_3_retry_cycle(self):
        """Walk through a complete 3-retry cycle: 3 LOOPs then LIMIT."""
        self._set_context(logic_mode=MODE_RETRY, max_retries=3)
        spike = self._make_spike(axoplasm={})

        # Iteration 0 -> LOOP (count becomes 1)
        code, msg = self._run(spike)
        self.assertEqual(code, 200)
        self.assertIn('attempt 1 of 4', msg)
        spike.refresh_from_db()
        self.assertEqual(spike.axoplasm[BB_LOOP_COUNT], 1)

        # Iteration 1 -> LOOP (count becomes 2)
        code, msg = self._run(spike)
        self.assertEqual(code, 200)
        self.assertIn('attempt 2 of 4', msg)
        spike.refresh_from_db()
        self.assertEqual(spike.axoplasm[BB_LOOP_COUNT], 2)

        # Iteration 2 -> LOOP (count becomes 3)
        code, msg = self._run(spike)
        self.assertEqual(code, 200)
        self.assertIn('attempt 3 of 4', msg)
        spike.refresh_from_db()
        self.assertEqual(spike.axoplasm[BB_LOOP_COUNT], 3)

        # Iteration 3 -> LIMIT REACHED
        code, msg = self._run(spike)
        self.assertEqual(code, 500)
        self.assertIn('LIMIT REACHED', msg)
        self.assertIn('attempt 4 of 4', msg)
