from unittest.mock import patch
from django.test import TestCase
from talos_frontal.logic import process_stimulus
from talos_thalamus.models import Stimulus
from talos_thalamus.types import SignalTypeID
from hydra.models import HydraSpawn, HydraSpellbook, HydraSpawnStatus
from talos_reasoning.models import ReasoningSession, ReasoningStatusID


class RealWorldCognitionTest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
        'talos_frontal/fixtures/initial_data.json',
        'talos_reasoning/fixtures/initial_data.json'
    ]

    def setUp(self):
        self.book = HydraSpellbook.objects.create(name="RealBook")
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, status_id=HydraSpawnStatus.FAILED)

    @patch('talos_frontal.logic.read_build_log')
    # FIX: Patch the Engine's client, NOT the logic module's client (which is gone)
    @patch('talos_reasoning.engine.OllamaClient')
    def test_auto_drive_loop(self, mock_engine_client, mock_log):
        """
        Verify that the loop in logic.py correctly drives the engine multiple times
        until the goal is complete.
        """
        mock_log.return_value = "ERROR SUMMARY: Missing file."

        client = mock_engine_client.return_value
        client.chat.side_effect = [
            # Turn 1: Action (New Syntax)
            {
                "content": "READ_FILE: config.ini"
            },
            # Turn 2: Conclusion
            {
                "content": "The file is missing. Fix it."
            },
            # Summary
            {
                "content": "Summary."
            }
        ]

        process_stimulus(
            Stimulus('hydra', 'Fail', {
                'spawn_id': self.spawn.id,
                'event_type': SignalTypeID.SPAWN_FAILED
            }))

        session = ReasoningSession.objects.get(spawn_link=self.spawn)

        # Should have 2 turns
        self.assertEqual(session.turns.count(), 2)

        # Verify Session Status is COMPLETED (Loop finished)
        self.assertEqual(session.status_id, ReasoningStatusID.COMPLETED)

        # Verify Tool Call happened (via Engine logic)
        first_turn = session.turns.order_by('turn_number').first()
        self.assertTrue(first_turn.tool_calls.exists())
        self.assertEqual(first_turn.tool_calls.first().tool.name,
                         'ai_read_file')
