from unittest.mock import patch, MagicMock
from django.test import TestCase
from talos_frontal.logic import process_stimulus
from talos_frontal.models import ConsciousStream, ConsciousStatusID
from talos_thalamus.models import Stimulus
from talos_thalamus.types import SignalTypeID
from hydra.models import HydraSpawn, HydraSpellbook, HydraEnvironment, HydraSpawnStatus
from environments.models import ProjectEnvironment


class RealWorldCognitionTest(TestCase):
    fixtures = [
        'talos_frontal/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json',
        'environments/fixtures/initial_data.json'
    ]

    def setUp(self):
        self.env = ProjectEnvironment.objects.create(name="RealEnv", project_root="C:/Real", is_active=True)
        self.h_env = HydraEnvironment.objects.create(project_environment=self.env)
        self.book = HydraSpellbook.objects.create(name="RealBook")
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, environment=self.h_env, status_id=HydraSpawnStatus.FAILED
        )

    @patch('talos_frontal.logic.read_build_log')
    @patch('talos_frontal.logic.OllamaClient')
    @patch('talos_frontal.logic.ai_read_file')
    def test_hallucinated_syntax_loop(self, mock_scry, mock_ollama_cls, mock_log):
        """
        Simulates the AI using ':::ai_read_file(path="...") :::' syntax.
        Verifies the parser catches it, executes the tool, and feeds it back.
        """
        # 1. Setup Context
        mock_log.return_value = "Error: Missing file in Config."

        # 2. Setup AI Turn responses
        client = mock_ollama_cls.return_value

        # Turn 1: AI hallucinates Python syntax
        response_1 = {
            "content": "Checking config.\n:::ai_read_file(path=\"Config/DefaultEngine.ini\") :::",
            "tokens_input": 10, "tokens_output": 10, "model": "test-model"
        }

        # Turn 2: AI receives file content and concludes
        response_2 = {
            "content": "The file is empty. Fix it.",
            "tokens_input": 20, "tokens_output": 10, "model": "test-model"
        }

        client.chat.side_effect = [response_1, response_2]

        # Mock Tool Execution
        mock_scry.return_value = "[Ini Content]"

        # 3. Trigger
        process_stimulus(
            Stimulus('hydra', 'Fail', {'spawn_id': self.spawn.id, 'event_type': SignalTypeID.SPAWN_FAILED}))

        # 4. Assertions

        # Did we actually call the tool despite the weird syntax?
        mock_scry.assert_called_with(
            "Config/DefaultEngine.ini",
            root_path='C:/Real',
            start_line=1,
            max_lines=50
        )

        # Did the stream capture the conversation?
        stream = ConsciousStream.objects.get(spawn_link=self.spawn)

        self.assertIn("> **read_file**", stream.current_thought)

        # Check Final Outcome
        self.assertIn("The file is empty", stream.current_thought)