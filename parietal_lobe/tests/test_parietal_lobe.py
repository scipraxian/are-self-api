import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

from common.tests.common_test_case import CommonFixturesAPITestCase
from identity.addons.focus_addon import FOCUS_ADDON_SLUG
from identity.models import (
    Identity,
    IdentityAddon,
    IdentityDisc,
    IdentityType,
)
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)
from parietal_lobe.models import (
    ToolCall,
    ToolDefinition,
    ToolParameter,
    ToolParameterAssignment,
    ToolParameterType,
    ToolUseType,
)
from parietal_lobe.parietal_lobe import ParietalLobe


class ParietalLobeTest(CommonFixturesAPITestCase):

    def setUp(self):
        # Create minimal required objects
        from central_nervous_system.models import (
            Spike,
            SpikeStatus,
            SpikeTrain,
            SpikeTrainStatus,
            NeuralPathway,
        )

        self.book = NeuralPathway.objects.create(name='Test Book')
        self.spike_train = SpikeTrain.objects.create(
            pathway=self.book, status_id=SpikeTrainStatus.RUNNING)
        self.spike = Spike.objects.create(spike_train=self.spike_train,
                                          status_id=SpikeStatus.RUNNING,
                                          axoplasm={})

        self.session = ReasoningSession.objects.create(
            spike=self.spike,
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=10,
            current_focus=5,
            total_xp=0,
        )

        # Attach an identity to the session so ParietalLobe can resolve enabled tools.
        worker_type, _ = IdentityType.objects.get_or_create(
            id=IdentityType.WORKER, defaults={'name': 'Worker'}
        )
        self.identity = Identity.objects.create(
            name='Test Identity',
            identity_type=worker_type,
            system_prompt_template='Test prompt',
        )
        # IdentityDisc now owns the identity fields directly; no FK to Identity.
        self.identity_disc = IdentityDisc.objects.create(
            name='Test Disc',
            identity_type=worker_type,
            system_prompt_template='Test prompt',
        )
        # Attach the Focus Game addon so the parietal lobe gates ON the
        # fizzle + focus/XP ledger. Tests that want the opt-out behavior
        # should remove this attachment (see
        # test_handle_tool_execution_no_focus_addon_no_fizzle below).
        # NOTE: fixtures ship an IdentityAddon pk=2 named 'The Focus Game'
        # with function_slug=None, so we can't reuse it — we need a row
        # whose slug matches FOCUS_ADDON_SLUG. Creating a fresh row here
        # keeps the test isolated from the fixture-backfill decision
        # (tracked in NEURAL_MODIFIER_COMPLETION_PLAN.md Task 18).
        self.focus_addon_row = IdentityAddon.objects.create(
            name='Focus Addon (test)',
            function_slug=FOCUS_ADDON_SLUG,
        )
        self.identity_disc.addons.add(self.focus_addon_row)
        self.session.identity_disc = self.identity_disc
        self.session.save(update_fields=['identity_disc'])

        self.turn = ReasoningTurn.objects.create(
            session=self.session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )

        # Create a mock log callback
        self.log_messages = []

        def mock_callback(msg):
            self.log_messages.append(msg)

        self.parietal_lobe = ParietalLobe(self.session, mock_callback)

    @pytest.mark.asyncio
    @patch('parietal_lobe.parietal_lobe.asyncio.to_thread')
    async def test_chat_conduit(self, mock_thread):
        """Test the stateless chat conduit."""
        from hypothalamus.serializers import ModelSelection
        from decimal import Decimal

        mock_selection = ModelSelection(
            provider_model_id='test-model-id',
            ai_model_name='test-model',
            distance=0.0,
            input_cost_per_token=Decimal('0.0001')
        )
        mock_thread.return_value = 'DUMMY_SYNAPSE_RESPONSE'

        resp = await self.parietal_lobe.chat(
            [{'role': 'user', 'content': 'hello'}],
            [],
            mock_selection
        )
        self.assertEqual(resp, 'DUMMY_SYNAPSE_RESPONSE')
        mock_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_build_tool_schemas(self):
        """Test the parameter-to-schema extraction logic."""
        tool_def, _ = await sync_to_async(ToolDefinition.objects.get_or_create)(
            name='mcp_dummy_tool',
            defaults={'description': 'A dummy tool.', 'is_async': True},
        )
        mechanics, _ = await sync_to_async(ToolUseType.objects.get_or_create)(
            name='Extraction',
            defaults={
                'focus_modifier': -2,
                'xp_reward': 5,
                'description': '',
            },
        )
        tool_def.use_type = mechanics
        await sync_to_async(tool_def.save)()

        # Ensure this tool is actually enabled for the session's IdentityDisc so that
        # ParietalLobe._fetch_tools() will include it.
        await sync_to_async(self.identity_disc.enabled_tools.add)(tool_def)

        t_str, _ = await sync_to_async(ToolParameterType.objects.get_or_create
                                      )(name='string')
        param = await sync_to_async(ToolParameter.objects.create
                                   )(name='dummy_arg',
                                     type=t_str,
                                     description='Arg desc')
        await sync_to_async(ToolParameterAssignment.objects.create
                           )(tool=tool_def, parameter=param, required=True)

        schemas = await self.parietal_lobe.build_tool_schemas()

        schema = next(
            (s for s in schemas if s['function']['name'] == 'mcp_dummy_tool'),
            None,
        )
        self.assertIsNotNone(schema, 'Dummy tool not found in schemas')

        self.assertEqual(schema['type'], 'function')
        self.assertEqual(schema['function']['name'], 'mcp_dummy_tool')
        self.assertIn(
            '[COST: -2 Focus | REWARD: +2 XP]',
            schema['function']['description'],
        )
        self.assertIn('dummy_arg', schema['function']['parameters']['required'])

    @pytest.mark.asyncio
    @patch('parietal_lobe.parietal_lobe.ParietalMCP.execute')
    async def test_handle_tool_execution_success(self, mock_execute):
        """Test valid execution with economy reward/cost."""
        mock_execute.return_value = 'DUMMY_RESULT'

        tool_def = await sync_to_async(ToolDefinition.objects.create)(
            name='mcp_dummy_tool',
            is_async=True,
        )
        mechanics = await sync_to_async(ToolUseType.objects.create)(
            focus_modifier=1,
            xp_reward=10,
        )
        tool_def.use_type = mechanics
        await sync_to_async(tool_def.save)()

        tool_call_data = {
            'function': {
                'name': 'mcp_dummy_tool',
                'arguments': '{"dummy_arg": "value"}',
            }
        }

        result = await self.parietal_lobe.handle_tool_execution(
            self.turn, tool_call_data)

        self.assertEqual(result['role'], 'tool')
        self.assertEqual(result['name'], 'mcp_dummy_tool')
        self.assertEqual(result['content'], 'DUMMY_RESULT')

        # Check economy logic
        await sync_to_async(self.session.refresh_from_db)()
        self.assertEqual(self.session.current_focus, 6)  # 5 + 1
        self.assertEqual(self.session.total_xp, 10)

        # Ensure the core arguments are passed through; additional metadata
        # (like session_id/turn_id) is allowed.
        args, kwargs = mock_execute.call_args
        self.assertEqual(args[0], 'mcp_dummy_tool')
        self.assertEqual(args[1]['dummy_arg'], 'value')

        # Verify db record
        tool_call = await sync_to_async(
            ToolCall.objects.filter(turn=self.turn).first)()
        self.assertIsNotNone(tool_call)
        self.assertEqual(tool_call.status_id, ReasoningStatusID.COMPLETED)
        self.assertEqual(tool_call.result_payload, 'DUMMY_RESULT')

    @pytest.mark.asyncio
    @patch('parietal_lobe.parietal_lobe.ParietalMCP.execute')
    async def test_handle_tool_execution_fizzle(self, mock_execute):
        """Test that a tool fizzles if there is insufficient focus."""
        tool_def = await sync_to_async(ToolDefinition.objects.create)(
            name='mcp_expensive_tool',
            is_async=True,
        )
        mechanics = await sync_to_async(ToolUseType.objects.create)(
            focus_modifier=-10,  # Costs 10, but session only has 5
            xp_reward=10,
        )
        tool_def.use_type = mechanics
        await sync_to_async(tool_def.save)()

        tool_call_data = {
            'function': {
                'name': 'mcp_expensive_tool',
                'arguments': '{}',
            }
        }

        result = await self.parietal_lobe.handle_tool_execution(
            self.turn, tool_call_data)

        mock_execute.assert_not_called()
        self.assertIn('SYSTEM OVERRIDE: Effector Fizzled!', result['content'])

        # Check economy unharmed
        await sync_to_async(self.session.refresh_from_db)()
        self.assertEqual(self.session.current_focus, 5)

        # Verify failure db record
        tool_call = await sync_to_async(
            ToolCall.objects.filter(turn=self.turn).first)()
        self.assertEqual(tool_call.status_id, ReasoningStatusID.ERROR)

    @pytest.mark.asyncio
    @patch('parietal_lobe.parietal_lobe.ParietalMCP.execute')
    async def test_handle_tool_execution_mcp_pass(self, mock_execute):
        """Test that calling mcp_pass fully restores focus pool."""

        # Note: the actual logic is in mcp_pass.py. We'll simulate its side effect
        # during execution, as that's what ParietalMCP.execute normally handles.
        async def mock_mcp_execute(*args, **kwargs):
            self.session.current_focus = self.session.max_focus
            await sync_to_async(self.session.save
                               )(update_fields=['current_focus'])
            return 'Turn passed. Focus pool fully restored.'

        mock_execute.side_effect = mock_mcp_execute

        tool_def = await sync_to_async(ToolDefinition.objects.get
                                      )(name='mcp_pass')

        tool_call_data = {
            'function': {
                'name': 'mcp_pass',
                'arguments': f'{{"session_id": "{self.session.id}"}}',
            }
        }

        # Ensure initial state
        self.assertTrue(self.session.current_focus < self.session.max_focus)

        result = await self.parietal_lobe.handle_tool_execution(
            self.turn, tool_call_data)

        self.assertEqual(result['role'], 'tool')
        self.assertEqual(result['name'], 'mcp_pass')

        # Focus should be maxed out unconditionally
        await sync_to_async(self.session.refresh_from_db)()
        self.assertEqual(self.session.current_focus, self.session.max_focus)

        args, kwargs = mock_execute.call_args
        self.assertEqual(args[0], 'mcp_pass')
        self.assertEqual(args[1]['session_id'], str(self.session.id))

    @pytest.mark.asyncio
    @patch('parietal_lobe.parietal_lobe.ParietalMCP.execute')
    async def test_handle_tool_execution_no_focus_addon_no_fizzle(
        self, mock_execute
    ):
        """Discs without the Focus Game addon must not fizzle or mutate focus.

        Regression guard: before the addon gate landed, parietal_lobe enforced
        the focus economy on every disc unconditionally, breaking opt-out
        spiketrains with 'Insufficient Focus' fizzles the first time they
        tried an expensive tool. Removing the focus_addon attachment here
        simulates an opt-out disc; the tool must execute normally and the
        session's current_focus/total_xp must not move.
        """
        # Remove the focus_addon attachment set up in setUp(), and rebuild
        # the ParietalLobe so its cached _focus_enabled flag is fresh.
        await sync_to_async(self.identity_disc.addons.remove)(
            self.focus_addon_row
        )
        self.parietal_lobe = ParietalLobe(self.session, lambda msg: None)

        mock_execute.return_value = 'DUMMY_RESULT'

        tool_def = await sync_to_async(ToolDefinition.objects.create)(
            name='mcp_expensive_tool',
            is_async=True,
        )
        mechanics = await sync_to_async(ToolUseType.objects.create)(
            focus_modifier=-10,  # Would fizzle a disc that had the addon.
            xp_reward=10,
        )
        tool_def.use_type = mechanics
        await sync_to_async(tool_def.save)()

        tool_call_data = {
            'function': {
                'name': 'mcp_expensive_tool',
                'arguments': '{}',
            }
        }

        result = await self.parietal_lobe.handle_tool_execution(
            self.turn, tool_call_data
        )

        # Tool actually ran — no fizzle short-circuit.
        mock_execute.assert_called_once()
        self.assertEqual(result['content'], 'DUMMY_RESULT')
        self.assertNotIn(
            'SYSTEM OVERRIDE: Effector Fizzled!', result['content']
        )

        # Ledger did not move — the addon is the single source of truth for
        # the economy, and it isn't attached.
        await sync_to_async(self.session.refresh_from_db)()
        self.assertEqual(self.session.current_focus, 5)
        self.assertEqual(self.session.total_xp, 0)

        # ToolCall row still records the execution as COMPLETED.
        tool_call = await sync_to_async(
            ToolCall.objects.filter(turn=self.turn).first
        )()
        self.assertEqual(tool_call.status_id, ReasoningStatusID.COMPLETED)
