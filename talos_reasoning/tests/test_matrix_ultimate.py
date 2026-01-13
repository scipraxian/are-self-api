import os
import shutil
import tempfile
from django.test import TestCase, SimpleTestCase, override_settings
from unittest.mock import patch
from talos_frontal.utils import parse_command_string
from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import (ReasoningSession, ReasoningGoal,
                                    ReasoningStatusID, ToolCall)


class ParserStressTest(SimpleTestCase):
    """Test 1: Parser Stress - CLI Syntax."""

    def test_parser_variations(self):
        variations = [
            ('READ_FILE: A.py', "A.py"),
            ('READ_FILE: B.py 100', "B.py"),
            ('SEARCH_FILE: C.py "foobar"', "C.py"),
            ('Some thought.\nREAD_FILE: D.py', "D.py"),
        ]
        for text, expected in variations:
            with self.subTest(msg=f"Testing: {text}"):
                action = parse_command_string(text)
                self.assertIsNotNone(action)
                self.assertEqual(action['args']['path'], expected)


class ReasoningMatrixTest(TestCase):
    """Comprehensive integration and logic tests for the Engine."""
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        self.session = ReasoningSession.objects.create(
            goal="Main Mission",
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=10)
        self.engine = ReasoningEngine()
        self.tmp_root = tempfile.mkdtemp()
        self.real_file = os.path.join(self.tmp_root, "real.txt")
        with open(self.real_file, "w") as f:
            f.write("CONTENT_ALPHA")
        self.settings_override = override_settings(BASE_DIR=self.tmp_root)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.tmp_root)

    @patch('talos_reasoning.engine.OllamaClient')
    def test_goal_switching_interrupt(self, mock_client_cls):
        """Test 2: Goal Switching - PENDING goals must interrupt and isolate context."""
        mock_instance = mock_client_cls.return_value

        # Goal A
        mock_instance.chat.side_effect = [
            {"content": "READ_FILE: A.txt"},
            {"content": "Summary A"}
        ]

        # Step A: Run Goal A
        goal_a = ReasoningGoal.objects.create(
            session=self.session,
            reasoning_prompt="Read A",
            status_id=ReasoningStatusID.PENDING)
        self.engine.tick(self.session.id)

        # Because we are linear now, tick() does one step.
        # We assume the user would create Goal B next.
        goal_a.status_id = ReasoningStatusID.COMPLETED
        goal_a.save()
        self.session.rolling_context_summary = "Summary A"
        self.session.save()

        # Step B: Inject Goal B
        goal_b = ReasoningGoal.objects.create(
            session=self.session,
            reasoning_prompt="Read B",
            status_id=ReasoningStatusID.PENDING)

        mock_instance.chat.side_effect = [{"content": "READ_FILE: B.txt"}]

        self.engine.tick(self.session.id)

        # Isolated context check
        turn_b = self.session.turns.filter(active_goal=goal_b).first()
        self.assertNotIn("A.txt", turn_b.input_context_snapshot)
        self.assertIn("Summary A", turn_b.input_context_snapshot)

    @patch('talos_reasoning.engine.OllamaClient')
    def test_hallucination_recovery(self, mock_client_cls):
        """Test 3: Hallucination Recovery."""
        mock_instance = mock_client_cls.return_value

        mock_instance.chat.return_value = {"content": "READ_FILE: fake.txt"}

        self.engine.tick(self.session.id)

        call = ToolCall.objects.filter(turn__session=self.session).first()
        self.assertIn("not found", call.result_payload)

    @patch('talos_reasoning.engine.OllamaClient')
    def test_tool_safety_and_implicit_root(self, mock_client_cls):
        """Test 4: Tool Safety."""
        mock_instance = mock_client_cls.return_value
        mock_instance.chat.return_value = {"content": "READ_FILE: ../secrets.txt"}

        self.engine.tick(self.session.id)
        call = ToolCall.objects.filter(turn__session=self.session).first()
        self.assertIn("Access denied", call.result_payload)

    @patch('talos_reasoning.engine.OllamaClient')
    def test_live_sim_mocked(self, mock_client_cls):
        """Test 5: Live Simulation."""
        mock_instance = mock_client_cls.return_value
        mock_instance.chat.return_value = {"content": "LIST_DIR: ."}

        self.engine.tick(self.session.id)
        turn = self.session.turns.first()
        call = turn.tool_calls.first()
        self.assertEqual(call.tool.name, "ai_list_files")
        self.assertIn("real.txt", call.result_payload)