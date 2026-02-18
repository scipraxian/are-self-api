import uuid
from unittest.mock import patch

from django.test import TestCase

from hydra.models import (
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpellbook,
)
from hydra.spells.spell_casters.spell_handlers.frontal_lobe_handler import (
    FrontalLobeConstants,
    run_frontal_lobe,
)
from talos_parietal.models import ToolDefinition
from talos_parietal.synapse import OllamaResponse


class FrontalLobeHandlerTest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
    ]

    def setUp(self):
        # Base Data
        self.book = HydraSpellbook.objects.create(name='Test Protocol')
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, status_id=HydraSpawnStatus.RUNNING
        )
        self.head = HydraHead.objects.create(
            spawn=self.spawn, status_id=HydraHeadStatus.RUNNING, blackboard={}
        )

        # Setup an MCP Tool
        self.tool_def = ToolDefinition.objects.create(
            name='ai_update_blackboard',
            description='Updates the blackboard.',
            parameters_schema={
                'type': 'object',
                'properties': {
                    'head_id': {'type': 'string'},
                    'key': {'type': 'string'},
                    'value': {'type': 'string'},
                },
            },
        )

    @patch(
        'hydra.spells.spell_casters.spell_handlers.frontal_lobe_handler.OllamaClient'
    )
    def test_handler_completes_without_tools(self, mock_client_cls):
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

        status_code, log = run_frontal_lobe(self.head.id)

        self.assertEqual(status_code, 200)
        self.assertIn('Objective Complete', log)

        # Verify it only ticked once
        mock_instance.chat.assert_called_once()

    @patch(
        'hydra.spells.spell_casters.spell_handlers.frontal_lobe_handler.OllamaClient'
    )
    def test_handler_executes_tool_and_loops(self, mock_client_cls):
        """Verify the handler can execute a tool, feed the result back, and loop."""
        mock_instance = mock_client_cls.return_value

        # Turn 1: Model requests a tool call
        resp_turn_1 = OllamaResponse(
            content='I need to update the blackboard.',
            tool_calls=[
                {
                    FrontalLobeConstants.T_FUNC: {
                        FrontalLobeConstants.T_NAME: 'ai_update_blackboard',
                        FrontalLobeConstants.T_ARGS: {
                            'head_id': str(self.head.id),
                            'key': 'test_var',
                            'value': 'alpha',
                        },
                    }
                }
            ],
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

        status_code, log = run_frontal_lobe(self.head.id)

        self.assertEqual(status_code, 200)
        self.assertIn('Tool Call: ai_update_blackboard', log)

        # Verify the tool actually ran and mutated the database
        self.head.refresh_from_db()
        self.assertEqual(self.head.blackboard.get('test_var'), 'alpha')

        # Verify it ticked twice
        self.assertEqual(mock_instance.chat.call_count, 2)

    @patch(
        'hydra.spells.spell_casters.spell_handlers.frontal_lobe_handler.OllamaClient'
    )
    def test_handler_max_turns_cutoff(self, mock_client_cls):
        """Verify the loop forcibly terminates if the AI gets stuck in a loop."""
        mock_instance = mock_client_cls.return_value

        # An AI that constantly requests a non-existent tool
        endless_resp = OllamaResponse(
            content='Let me try this again...',
            tool_calls=[
                {
                    FrontalLobeConstants.T_FUNC: {
                        FrontalLobeConstants.T_NAME: 'ai_hallucinated_tool',
                        FrontalLobeConstants.T_ARGS: {},
                    }
                }
            ],
            tokens_input=10,
            tokens_output=10,
            model='test_model',
        )

        # Feed the endless response
        mock_instance.chat.return_value = endless_resp

        status_code, log = run_frontal_lobe(self.head.id)

        self.assertEqual(status_code, 200)
        self.assertIn('Max cognitive turns reached', log)
        self.assertEqual(
            mock_instance.chat.call_count, FrontalLobeConstants.MAX_TURNS
        )
