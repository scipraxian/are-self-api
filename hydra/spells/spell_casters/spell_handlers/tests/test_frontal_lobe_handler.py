from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from django.test import TransactionTestCase

from hydra.models import (
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpellbook,
)
from talos_parietal.models import (
    ToolDefinition,
    ToolParameter,
    ToolParameterAssignment,
    ToolParameterType,
)
from talos_parietal.parietal_lobe import ParietalLobe
from frontal_lobe.synapse import OllamaResponse
from frontal_lobe.frontal_lobe import (
    FrontalLobeConstants,
    run_frontal_lobe,
)


# FIX 1: Use TransactionTestCase to prevent early DB rollbacks during async execution
class FrontalLobeHandlerTest(TransactionTestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
        'frontal_lobe/fixtures/initial_data.json',
        'talos_parietal/fixtures/initial_data.json',
    ]

    def setUp(self):
        # Base Data
        self.book = HydraSpellbook.objects.create(name='Test Protocol')
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, status_id=HydraSpawnStatus.RUNNING)
        self.head = HydraHead.objects.create(spawn=self.spawn,
                                             status_id=HydraHeadStatus.RUNNING,
                                             blackboard={})

        # FIX 2: Setup an MCP Tool with the strict 'mcp_' nomenclature
        self.tool_def, _ = ToolDefinition.objects.get_or_create(
            name='mcp_update_blackboard',)

        t_str, _ = ToolParameterType.objects.get_or_create(name='string')
        p_head_id, _ = ToolParameter.objects.get_or_create(
            name='head_id', defaults={'type': t_str})
        p_key, _ = ToolParameter.objects.get_or_create(name='key',
                                                       defaults={'type': t_str})
        p_val, _ = ToolParameter.objects.get_or_create(name='value',
                                                       defaults={'type': t_str})

        ToolParameterAssignment.objects.get_or_create(tool=self.tool_def,
                                                      parameter=p_head_id,
                                                      required=True)
        ToolParameterAssignment.objects.get_or_create(tool=self.tool_def,
                                                      parameter=p_key,
                                                      required=True)
        ToolParameterAssignment.objects.get_or_create(tool=self.tool_def,
                                                      parameter=p_val,
                                                      required=True)

    @pytest.mark.asyncio
    @patch('talos_parietal.parietal_lobe.OllamaClient')
    async def test_handler_completes_without_tools(self, mock_client_cls):
        """Verify the loop exits gracefully if the AI outputs no tool calls."""
        mock_instance = mock_client_cls.return_value

        # Mock an AI response with just a thought, no tools
        mock_instance.chat.return_value = OllamaResponse(
            content='I have analyzed the context and no action is required.',
            tool_calls=[],
            tokens_input=10,
            tokens_output=15,
            model='test_model',
        )

        status_code, log = await run_frontal_lobe(self.head.id)

        self.assertEqual(status_code, 200)
        self.assertIn('Permanent Sleep Initiated.', log)

    @pytest.mark.asyncio
    @patch('talos_parietal.parietal_lobe.OllamaClient')
    async def test_handler_executes_tool_and_loops(self, mock_client_cls):
        """Verify the handler can execute a tool, feed the result back, and loop."""
        mock_instance = mock_client_cls.return_value

        # Turn 1: Model requests a tool call (using correct mcp_ name)
        resp_turn_1 = OllamaResponse(
            content='I need to update the blackboard.',
            tool_calls=[{
                ParietalLobe.T_FUNC: {
                    ParietalLobe.T_NAME: 'mcp_update_blackboard',
                    ParietalLobe.T_ARGS: {
                        'head_id': str(self.head.id),
                        'key': 'test_var',
                        'value': 'alpha',
                    },
                }
            }],
            tokens_input=10,
            tokens_output=10,
            model='test_model',
        )

        # Turn 2: Model finishes the job
        resp_turn_2 = OllamaResponse(
            content='Blackboard updated. I am done.',
            tool_calls=[],
            tokens_input=10,
            tokens_output=10,
            model='test_model',
        )

        mock_instance.chat.side_effect = [resp_turn_1, resp_turn_2]

        status_code, log = await run_frontal_lobe(self.head.id)

        self.assertEqual(status_code, 200)
        self.assertIn('Tool Call: mcp_update_blackboard', log)

        # Verify the tool ACTUALLY ran and mutated the database
        await sync_to_async(self.head.refresh_from_db)()
        self.assertEqual(self.head.blackboard.get('test_var'), 'alpha')
        self.assertEqual(mock_instance.chat.call_count, 2)

    @pytest.mark.asyncio
    @patch('frontal_lobe.frontal_lobe.FrontalLobeConstants.DEFAULT_MAX_TURNS',
           3)
    @patch('talos_parietal.parietal_lobe.OllamaClient')
    async def test_handler_max_turns_cutoff(self, mock_client_cls):
        """Verify the loop forcibly terminates if the AI gets stuck in a loop."""
        mock_instance = mock_client_cls.return_value

        endless_resp = OllamaResponse(
            content='Let me try this again...',
            tool_calls=[{
                ParietalLobe.T_FUNC: {
                    ParietalLobe.T_NAME: 'mcp_hallucinated_tool',
                    ParietalLobe.T_ARGS: {},
                }
            }],
            tokens_input=10,
            tokens_output=10,
            model='test_model',
        )

        mock_instance.chat.return_value = endless_resp

        status_code, log = await run_frontal_lobe(self.head.id)

        self.assertEqual(status_code, 200)

        # FIX 3: Match the exact string from the engine's log
        self.assertIn('Max turns reached', log)
