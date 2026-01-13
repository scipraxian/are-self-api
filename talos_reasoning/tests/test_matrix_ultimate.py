import os
import shutil
import tempfile
import json
from django.test import TestCase, SimpleTestCase, override_settings
from unittest.mock import patch, MagicMock
from talos_frontal.utils import parse_ai_actions
from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import (ReasoningSession, ReasoningGoal,
                                    ReasoningTurn, ReasoningStatusID,
                                    ToolDefinition, ToolCall)


class ParserStressTest(SimpleTestCase):
    """Test 1: Parser Stress - Robustness against various syntax styles."""

    def test_parser_variations(self):
        variations = [
            (':::ai_read_file(path="A.py") :::', "A.py"),
            (':::ai_read_file("B.py")', "B.py"),
            ('::: ai_read_file ( path = "C.py" ) :::', "C.py"),
            (":::ai_read_file(path='D.py') :::", "D.py"),
            (':::\nai_read_file(\npath="E.py"\n)\n:::', "E.py"),
            (':::ai_read_file("F.py") :::', "F.py"),
            (':::ACTION {"tool": "ai_read_file", "args": {"path": "G.py"}} :::',
             "G.py"),
            ('Check this: :::ai_read_file(path="H.py") and then :::ai_search_file(path="I.py", pattern="foo") :::',
             "H.py")
        ]
        for text, expected in variations:
            with self.subTest(msg=f"Testing: {text}"):
                actions = parse_ai_actions(text)
                self.assertGreaterEqual(len(actions), 1,
                                        f"Failed to parse: {text}")
                self.assertEqual(actions[0]['args']['path'], expected)


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

        # Responses for Goal A: 1: Tool, 2: Synthesis, 3: Summary
        mock_instance.chat.side_effect = [
            {
                "content": "THOUGHT: Read A\n:::ai_read_file(path='A.txt') :::"
            },
            {
                "content": "THOUGHT: Synthesis A"
            },
            {
                "content": "Summary A"
            },
            # Goal B follows
            {
                "content": "THOUGHT: Read B\n:::ai_read_file(path='B.txt') :::"
            },
            {
                "content": "Synthesis B"
            },
            {
                "content": "Summary B"
            }
        ]

        # Step A: Run Goal A
        goal_a = ReasoningGoal.objects.create(
            session=self.session,
            reasoning_prompt="Read A",
            status_id=ReasoningStatusID.PENDING)
        self.engine.tick(self.session.id)

        goal_a.refresh_from_db()
        self.assertEqual(goal_a.status_id, ReasoningStatusID.COMPLETED)

        # Step B: Inject Goal B (Interrupt - though Goal A is done now, let's test isolation)
        goal_b = ReasoningGoal.objects.create(
            session=self.session,
            reasoning_prompt="Read B",
            status_id=ReasoningStatusID.PENDING)
        self.engine.tick(self.session.id)

        # Isolated context check
        turn_b = self.session.turns.filter(active_goal=goal_b).first()
        self.assertNotIn("A.txt", turn_b.input_context_snapshot)
        self.assertIn("Summary A", turn_b.input_context_snapshot)

    @patch('talos_reasoning.engine.OllamaClient')
    def test_hallucination_recovery(self, mock_client_cls):
        """Test 3: Hallucination Recovery - Verify system handles file errors and continues."""
        mock_instance = mock_client_cls.return_value

        # Side effect: 1: Fake, 2: Real, 3: Synthesis, 4: Summary
        mock_instance.chat.side_effect = [{
            "content": ":::ai_read_file(path='fake.txt') :::"
        }, {
            "content": ":::ai_read_file(path='real.txt') :::"
        }, {
            "content": "Done."
        }, {
            "content": "Summary."
        }]

        self.engine.tick(self.session.id)

        calls = ToolCall.objects.filter(
            turn__session=self.session).order_by('created')
        self.assertGreaterEqual(calls.count(), 2)
        self.assertIn("not found", calls[0].result_payload)
        self.assertIn("CONTENT_ALPHA", calls[1].result_payload)

    @patch('talos_reasoning.engine.OllamaClient')
    def test_tool_safety_and_implicit_root(self, mock_client_cls):
        """Test 4: Tool Safety & Implicit Root - Verify jailbreak prevention."""
        mock_instance = mock_client_cls.return_value
        mock_instance.chat.side_effect = [{
            "content": ":::ai_read_file(path='../secrets.txt') :::"
        }, {
            "content": "Aborting."
        }, {
            "content": "Summary."
        }]

        self.engine.tick(self.session.id)
        call = ToolCall.objects.filter(turn__session=self.session).first()
        self.assertIn("Access denied", call.result_payload)

    @patch('talos_reasoning.engine.OllamaClient')
    def test_live_sim_mocked(self, mock_client_cls):
        """Test 5: Live Simulation - Verify end-to-end relational flow."""
        mock_instance = mock_client_cls.return_value
        mock_instance.chat.side_effect = [{
            "content": ":::ai_list_files(path='.') :::"
        }, {
            "content": "Synthesis."
        }, {
            "content": "Summary."
        }]

        self.engine.tick(self.session.id)
        turn = self.session.turns.first()
        call = turn.tool_calls.first()
        self.assertEqual(call.tool.name, "ai_list_files")
        self.assertIn("real.txt", call.result_payload)
