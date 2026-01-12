import os
import shutil
import tempfile
from unittest.mock import patch, MagicMock
from django.test import TestCase

from talos_frontal.utils import parse_ai_actions
from talos_parietal.tools import ai_read_file, ai_execute_task, ai_search_file
from talos_frontal.logic import process_stimulus
from talos_frontal.models import ConsciousStream, ConsciousStatusID
from talos_thalamus.models import Stimulus
from talos_thalamus.types import SignalTypeID
from hydra.models import HydraSpawn, HydraSpellbook, HydraEnvironment, HydraSpawnStatus
from environments.models import ProjectEnvironment


class SpellcasterUtilsTest(TestCase):
    def test_parse_valid_action(self):
        text = """
        I need to check the config.
        :::ACTION {"tool": "ai_read_file", "args": {"path": "config.ini"}} :::
        That should tell us more.
        """
        actions = parse_ai_actions(text)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['tool'], "ai_read_file")
        self.assertEqual(actions[0]['args']['path'], "config.ini")

    def test_parse_drifted_python_syntax(self):
        text = ':::ai_read_file(path="config.ini") :::'
        actions = parse_ai_actions(text)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['tool'], "ai_read_file")
        self.assertEqual(actions[0]['args']['path'], "config.ini")


class ToolTest(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        # Create a dummy file
        self.fpath = os.path.join(self.temp_dir, "test.txt")
        with open(self.fpath, "w") as f:
            f.write("Hello World\nLine 2\nLine 3")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_ai_read_file_read(self):
        # Pass root_path explicitly to simulate logic.py behavior
        content = ai_read_file("test.txt", root_path=self.temp_dir)
        self.assertIn("Hello World", content)

    def test_ai_read_file_traversal_attempt(self):
        """Test the explicit security check."""
        # UPDATE: Expect the new "Access denied" message from commonpath check
        result = ai_read_file("../outside.txt", root_path=self.temp_dir)
        self.assertIn("Access denied", result)

    def test_ai_search_file(self):
        # Pass root_path explicitly
        result = ai_search_file("test.txt", "Line 2", root_path=self.temp_dir)
        self.assertIn("Match 1", result)
        self.assertIn("Line 2", result)

    @patch('talos_parietal.tools.cast_hydra_spell.delay')
    def test_cast_spell(self, mock_celery):
        valid_uuid = "00000000-0000-0000-0000-000000000000"
        result = ai_execute_task(valid_uuid)
        self.assertIn("Successfully queued", result)
        mock_celery.assert_called_with(valid_uuid)


class CognitiveLoopTest(TestCase):
    fixtures = [
        'talos_frontal/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json',
        'environments/fixtures/initial_data.json'
    ]

    def setUp(self):
        self.book = HydraSpellbook.objects.create(name="TestBook")
        # CRITICAL FIX: We MUST provide project_root so logic.py can extract it
        self.env = ProjectEnvironment.objects.create(
            name="TestEnv",
            is_active=True,
            project_root="C:/FakeProject"
        )
        self.h_env = HydraEnvironment.objects.create(project_environment=self.env)
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book,
            environment=self.h_env,
            status_id=HydraSpawnStatus.FAILED
        )

    @patch('talos_frontal.logic.read_build_log')
    @patch('talos_frontal.logic.OllamaClient')
    @patch('talos_frontal.logic.ai_read_file')
    def test_multiturn_tool_execution(self, mock_ai_read_file, mock_ollama_cls, mock_read_log):
        # 1. Setup Inputs
        mock_read_log.return_value = "Error: Config missing."

        # 2. Setup AI Responses
        client = mock_ollama_cls.return_value

        # Turn 1: AI asks to read a file (Python syntax)
        response_turn_1 = {
            "content": ':::ai_read_file(path="config.ini") :::',
            "tokens_input": 10, "tokens_output": 10, "model": "test-bot"
        }

        # Turn 2: Conclusion
        response_turn_2 = {
            "content": "The config is empty.",
            "tokens_input": 20, "tokens_output": 10, "model": "test-bot"
        }

        client.chat.side_effect = [response_turn_1, response_turn_2]
        mock_ai_read_file.return_value = "[Config Content]"

        # 3. Trigger Stimulus
        process_stimulus(Stimulus('hydra', 'Fail', {
            'spawn_id': self.spawn.id,
            'event_type': SignalTypeID.SPAWN_FAILED
        }))

        # 4. Verification
        stream = ConsciousStream.objects.get(spawn_link=self.spawn)

        # Check call args - Ensure root_path was passed correctly
        mock_ai_read_file.assert_called_with("config.ini", root_path="C:/FakeProject")

        # Check conversation history update
        self.assertIn("--- TOOL EXECUTION ---", stream.current_thought)
        self.assertIn("Result (ai_read_file): [Config Content]", stream.current_thought)