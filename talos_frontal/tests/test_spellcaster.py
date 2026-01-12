import os
import shutil
import tempfile
from unittest.mock import patch, MagicMock
from django.test import TestCase

from talos_frontal.utils import parse_ai_actions
from talos_parietal.tools import ai_read_file, ai_execute_task
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

    def test_parse_multiple_actions(self):
        text = """
        :::ACTION {"tool": "a", "args": {}} :::
        :::ACTION {"tool": "b", "args": {}} :::
        """
        actions = parse_ai_actions(text)
        self.assertEqual(len(actions), 2)

    def test_parse_malformed_json(self):
        text = ":::ACTION {bad_json} :::"
        actions = parse_ai_actions(text)
        self.assertEqual(len(actions), 0)


class ToolTest(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        # Mock settings.BASE_DIR to be this temp dir for safety tests
        self.patcher = patch('talos_parietal.tools.settings')
        self.mock_settings = self.patcher.start()
        self.mock_settings.BASE_DIR = self.temp_dir

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.temp_dir)

    def test_ai_read_file_read(self):
        fpath = os.path.join(self.temp_dir, "test.txt")
        with open(fpath, "w") as f:
            f.write("Hello World")

        content = ai_read_file("test.txt")
        self.assertEqual(content, "Hello World")

    def test_ai_read_file_traversal_attempt(self):
        """Test the explicit '..' check."""
        result = ai_read_file("../outside.txt")
        self.assertIn("Directory traversal attempt", result)

    @patch('talos_parietal.tools.cast_hydra_spell.delay')
    def test_cast_spell(self, mock_celery):
        # FIX: Use a valid UUID string, not an integer
        valid_uuid = "00000000-0000-0000-0000-000000000000"
        result = ai_execute_task(valid_uuid)

        self.assertIn("Successfully cast spell", result)
        mock_celery.assert_called_with(valid_uuid)

    def test_cast_spell_invalid_uuid(self):
        """Verify the tool rejects garbage IDs gracefully."""
        result = ai_execute_task("not-a-uuid")
        self.assertIn("Error: Invalid Head ID", result)

class CognitiveLoopTest(TestCase):
    # Load required fixtures for the full brain loop
    fixtures = [
        'talos_frontal/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json',
        'environments/fixtures/initial_data.json'
    ]

    def setUp(self):
        self.book = HydraSpellbook.objects.create(name="TestBook")
        self.env = ProjectEnvironment.objects.create(name="TestEnv", is_active=True)
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
        """
        Verify the AI can:
        1. Receive a stimulus
        2. Decide to use a tool (Turn 1)
        3. Receive the tool result
        4. Make a final conclusion (Turn 2)
        """
        # 1. Setup Inputs
        mock_read_log.return_value = "Error: Config missing."

        # 2. Setup AI Responses (Turn 1: Tool, Turn 2: Final)
        mock_client = mock_ollama_cls.return_value

        # RESPONSE 1: AI asks to read a file
        response_turn_1 = {
            "content": "I see the error. Let me check the config.\n:::ACTION {\"tool\": \"ai_read_file\", \"args\": {\"path\": \"config.ini\"}} :::",
            "tokens_input": 10, "tokens_output": 10, "model": "test-bot"
        }

        # RESPONSE 2: AI reacts to the file content
        response_turn_2 = {
            "content": "The config is empty. I recommend rebuilding.",
            "tokens_input": 20, "tokens_output": 10, "model": "test-bot"
        }

        # Queue the responses
        mock_client.chat.side_effect = [response_turn_1, response_turn_2]

        # Mock Tool Result (What ai_read_file returns)
        mock_ai_read_file.return_value = "[Config Content]"

        # 3. Trigger Stimulus
        stimulus = Stimulus(source='hydra', description="Fail", context_data={
            'spawn_id': self.spawn.id,
            'event_type': SignalTypeID.SPAWN_FAILED
        })

        process_stimulus(stimulus)

        # 4. Verification
        stream = ConsciousStream.objects.get(spawn_link=self.spawn)

        # A. Check that ai_read_file was actually called by the logic
        mock_ai_read_file.assert_called_with("config.ini")

        # B. Check that the final thought contains the tool result
        # (This proves the loop fed the result back into the prompt/history)
        self.assertIn("--- TOOL EXECUTION ---", stream.current_thought)
        self.assertIn("Result (ai_read_file): [Config Content]", stream.current_thought)

        # C. Check final conclusion
        self.assertIn("The config is empty", stream.current_thought)