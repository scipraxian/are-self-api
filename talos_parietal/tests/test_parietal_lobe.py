import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from django.test import TransactionTestCase

from talos_parietal.models import (
    ToolCall,
    ToolDefinition,
    ToolParameter,
    ToolParameterAssignment,
    ToolParameterType,
    ToolUseType,
)
from talos_parietal.parietal_lobe import ParietalLobe
from talos_reasoning.models import (
    ReasoningGoal,
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)


class ParietalLobeTest(TransactionTestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
        'talos_reasoning/fixtures/initial_data.json',
        'talos_parietal/fixtures/initial_data.json',
    ]

    def setUp(self):
        # Create minimal required objects
        from hydra.models import HydraHead, HydraHeadStatus, HydraSpawn, HydraSpawnStatus, HydraSpellbook
        self.book = HydraSpellbook.objects.create(name='Test Book')
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, status_id=HydraSpawnStatus.RUNNING)
        self.head = HydraHead.objects.create(spawn=self.spawn,
                                             status_id=HydraHeadStatus.RUNNING,
                                             blackboard={})

        self.session = ReasoningSession.objects.create(
            head=self.head,
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=10,
            current_focus=5,
            total_xp=0,
        )

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
    @patch('talos_parietal.parietal_lobe.OllamaClient')
    async def test_initialize_and_chat(self, mock_client_cls):
        """Test inference flow wrapper."""
        mock_instance = mock_client_cls.return_value
        mock_instance.chat = MagicMock(return_value='test_response')

        await self.parietal_lobe.initialize_client('test_model')

        self.assertEqual(self.parietal_lobe.client, mock_instance)

        resp = await self.parietal_lobe.chat([{
            'role': 'user',
            'content': 'hello'
        }], [])
        self.assertEqual(resp, 'test_response')
        mock_instance.chat.assert_called_once()

        await self.parietal_lobe.unload_client()
        mock_instance.unload.assert_called_once()

    @pytest.mark.asyncio
    async def test_build_tool_schemas(self):
        """Test the parameter-to-schema extraction logic."""
        tool_def, _ = await sync_to_async(ToolDefinition.objects.get_or_create)(
            name='mcp_dummy_tool',
            defaults={
                'description': 'A dummy tool.',
                'is_async': True
            },
        )
        mechanics, _ = await sync_to_async(ToolUseType.objects.get_or_create)(
            name='Extraction',
            defaults={
                'focus_modifier': -2,
                'xp_reward': 5,
                'description': ''
            },
        )
        tool_def.use_type = mechanics
        await sync_to_async(tool_def.save)()

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
            None)
        self.assertIsNotNone(schema, "Dummy tool not found in schemas")

        self.assertEqual(schema['type'], 'function')
        self.assertEqual(schema['function']['name'], 'mcp_dummy_tool')
        self.assertIn('[COST: -2 Focus | REWARD: +2 XP]',
                      schema['function']['description'])
        self.assertIn('dummy_arg', schema['function']['parameters']['required'])

    @pytest.mark.asyncio
    @patch('talos_parietal.parietal_lobe.ParietalMCP.execute')
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

        mock_execute.assert_called_with('mcp_dummy_tool',
                                        {'dummy_arg': 'value'})

        # Verify db record
        tool_call = await sync_to_async(
            ToolCall.objects.filter(turn=self.turn).first)()
        self.assertIsNotNone(tool_call)
        self.assertEqual(tool_call.status_id, ReasoningStatusID.COMPLETED)
        self.assertEqual(tool_call.result_payload, 'DUMMY_RESULT')

    @pytest.mark.asyncio
    @patch('talos_parietal.parietal_lobe.ParietalMCP.execute')
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
        self.assertIn('SYSTEM OVERRIDE: Spell Fizzled!', result['content'])

        # Check economy unharmed
        await sync_to_async(self.session.refresh_from_db)()
        self.assertEqual(self.session.current_focus, 5)

        # Verify failure db record
        tool_call = await sync_to_async(
            ToolCall.objects.filter(turn=self.turn).first)()
        self.assertEqual(tool_call.status_id, ReasoningStatusID.ERROR)
