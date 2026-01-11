from unittest.mock import patch, MagicMock
from django.test import TestCase
from hydra.models import HydraSpawn, HydraSpellbook, HydraEnvironment, HydraSpawnStatus
from talos_frontal.logic import process_stimulus
from talos_frontal.models import ConsciousStream, ConsciousStatusID
from talos_thalamus.models import Stimulus
from talos_thalamus.types import SignalTypeID


class ParanoidLogicTest(TestCase):
    fixtures = [
        'talos_frontal/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json',
        'environments/fixtures/initial_data.json'
    ]

    def setUp(self):
        # Create minimal required objects
        # We don't need real Environments/Spellbooks since we mock read_build_log,
        # but we need a valid spawn_id for the checks.
        self.book = HydraSpellbook.objects.create(name="TestBook")
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, status_id=HydraSpawnStatus.CREATED)

    @patch('talos_frontal.logic.read_build_log')
    @patch('talos_frontal.logic.OllamaClient')
    def test_spawn_failed_triggers_analysis(self, mock_ollama_cls,
                                            mock_read_log):
        """Scenario 1: Spawn Failed -> Analysis triggered."""
        mock_read_log.return_value = "ERROR SUMMARY:\nSome Error\n\nLAST 200 LINES:\n..."
        mock_client = mock_ollama_cls.return_value
        mock_client.chat.return_value = "AI Analysis Result"

        stimulus = Stimulus(source='hydra',
                            description="Spawn Failed",
                            context_data={
                                'spawn_id': self.spawn.id,
                                'event_type': SignalTypeID.SPAWN_FAILED
                            })

        process_stimulus(stimulus)

        stream = ConsciousStream.objects.get(spawn_link=self.spawn)
        self.assertEqual(stream.status_id, ConsciousStatusID.DONE)
        self.assertIn("AI Analysis Result", stream.current_thought)

    @patch('talos_frontal.logic.read_build_log')
    @patch('talos_frontal.logic.OllamaClient')
    def test_spawn_success_with_errors_triggers_analysis(
            self, mock_ollama_cls, mock_read_log):
        """Scenario 2: Spawn Success + Errors (Hidden Failure) -> Analysis triggered."""
        # This is the "Paranoid" verification
        mock_read_log.return_value = "ERROR SUMMARY:\nHidden Error\n\nLAST 200 LINES:\n..."
        mock_client = mock_ollama_cls.return_value
        mock_client.chat.return_value = "AI Analysis of Hidden Error"

        stimulus = Stimulus(source='hydra',
                            description="Spawn Succeeded",
                            context_data={
                                'spawn_id': self.spawn.id,
                                'event_type': SignalTypeID.SPAWN_SUCCESS
                            })

        process_stimulus(stimulus)

        stream = ConsciousStream.objects.get(spawn_link=self.spawn)
        self.assertEqual(stream.status_id, ConsciousStatusID.DONE)
        # Verify the paranoid thought override
        self.assertTrue(stream.current_thought.startswith("Analysis Complete"))
        # Wait, logic code sets thought to: "Analysis Complete:\n{analysis}"
        self.assertIn("AI Analysis of Hidden Error", stream.current_thought)

        # We can also check if the intermediate thought was set, but saving overwrites it.
        # So checking final state is best.

    @patch('talos_frontal.logic.read_build_log')
    def test_spawn_success_clean_log(self, mock_read_log):
        """Scenario 3: Spawn Success + Clean Log -> No Analysis."""
        mock_read_log.return_value = "LAST 200 LINES:\nAll good."

        stimulus = Stimulus(source='hydra',
                            description="Spawn Succeeded",
                            context_data={
                                'spawn_id': self.spawn.id,
                                'event_type': SignalTypeID.SPAWN_SUCCESS
                            })

        process_stimulus(stimulus)

        stream = ConsciousStream.objects.get(spawn_link=self.spawn)
        self.assertEqual(stream.status_id, ConsciousStatusID.DONE)
        self.assertEqual(stream.current_thought,
                         "Build Succeeded. Log Verified Clean.")
