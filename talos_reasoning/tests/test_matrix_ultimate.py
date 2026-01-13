import os
import shutil
import tempfile
import json
from django.test import TestCase, SimpleTestCase, override_settings
from unittest.mock import patch, MagicMock
from talos_frontal.utils import parse_ai_actions
from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import ReasoningSession, ReasoningGoal, ReasoningTurn, ReasoningStatusID, ToolDefinition, ToolCall


class ParserStressTest(SimpleTestCase):
    """
    Test 1: Parser Stress - Robustness against various syntax styles.
    """

    def test_parser_variations(self):
        variations = [
            # Standard
            (':::ai_read_file(path="A.py") :::', "A.py"),
            # Lazy
            (':::ai_read_file("B.py")', "B.py"),
            # Spaces
            ('::: ai_read_file ( path = "C.py" ) :::', "C.py"),
            # Single Quotes
            (":::ai_read_file(path='D.py') :::", "D.py"),
            # Newlines
            (':::\nai_read_file(\npath="E.py"\n)\n:::', "E.py"),
            # No path key (pos fallback)
            (':::ai_read_file("F.py") :::', "F.py"),
            # ACTION JSON
            (':::ACTION {"tool": "ai_read_file", "args": {"path": "G.py"}} :::',
             "G.py"),
            # Messy concat
            ('Check this: :::ai_read_file(path="H.py") and then :::ai_search_file(path="I.py", pattern="foo") :::',
             "H.py")
        ]

        for text, expected in variations:
            with self.subTest(msg=f"Testing: {text}"):
                actions = parse_ai_actions(text)
                self.assertGreaterEqual(len(actions), 1,
                                        f"Failed to parse: {text}")
                self.assertEqual(actions[0]['args']['path'], expected)

    def test_multi_action(self):
        text = ':::ai_read_file("A.txt") ::: and then :::ai_search_file(path="B.txt", pattern="foo") :::'
        actions = parse_ai_actions(text)
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]['tool'], 'ai_read_file')
        self.assertEqual(actions[1]['tool'], 'ai_search_file')
        self.assertEqual(actions[1]['args']['pattern'], 'foo')


class ReasoningMatrixTest(TestCase):
    """
    Comprehensive integration and logic tests for the Engine.
    """
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        self.session = ReasoningSession.objects.create(
            goal="Main Mission",
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=10)
        self.engine = ReasoningEngine()

        # Setup temp root for file tests
        self.tmp_root = tempfile.mkdtemp()
        self.real_file = os.path.join(self.tmp_root, "real.txt")
        with open(self.real_file, "w") as f:
            f.write("CONTENT_ALPHA")

        # We'll use settings override to point to this tmp_root during tests
        self.settings_override = override_settings(BASE_DIR=self.tmp_root)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.tmp_root)

    @patch('talos_reasoning.engine.OllamaClient')
    def test_goal_switching_interrupt(self, mock_client_cls):
        """
        Test 2: Goal Switching - PENDING goals must interrupt and isolate context.
        """
        mock_instance = mock_client_cls.return_value

        # Step A: First goal "Read A"
        goal_a = ReasoningGoal.objects.create(
            session=self.session,
            reasoning_prompt="Read A",
            status_id=ReasoningStatusID.PENDING)
        mock_instance.chat.return_value = {
            "content": "THOUGHT: Read A\n:::ai_read_file(path='A.txt') :::"
        }

        self.engine.tick(self.session.id)

        turn_1 = self.session.turns.first()
        self.assertEqual(turn_1.active_goal, goal_a)
        self.assertEqual(turn_1.tool_calls.first().tool.name, "ai_read_file")
        self.assertEqual(
            json.loads(turn_1.tool_calls.first().arguments)['path'], 'A.txt')

        # Step B: Inject "Read B" (Interrupt)
        goal_b = ReasoningGoal.objects.create(
            session=self.session,
            reasoning_prompt="Read B",
            status_id=ReasoningStatusID.PENDING)
        mock_instance.chat.return_value = {
            "content": "THOUGHT: Read B\n:::ai_read_file(path='B.txt') :::"
        }

        self.engine.tick(self.session.id)

        # Goal A should now be COMPLETED
        goal_a.refresh_from_db()
        self.assertEqual(goal_a.status_id, ReasoningStatusID.COMPLETED)

        turn_2 = self.session.turns.order_by('turn_number').last()
        self.assertEqual(turn_2.active_goal, goal_b)
        self.assertEqual(
            json.loads(turn_2.tool_calls.first().arguments)['path'], 'B.txt')

        # ISOLATION CHECK: Turn 2 input_context should NOT mention A.txt because of context isolation
        self.assertNotIn("A.txt", turn_2.input_context_snapshot)

    @patch('talos_reasoning.engine.OllamaClient')
    def test_hallucination_recovery(self, mock_client_cls):
        """
        Test 3: Hallucination Recovery - Verify system handles file errors and continues.
        """
        mock_instance = mock_client_cls.return_value

        # Step A: AI asks for fake.txt
        mock_instance.chat.return_value = {
            "content": ":::ai_read_file(path='fake.txt') :::"
        }
        self.engine.tick(self.session.id)

        call_1 = ToolCall.objects.filter(turn__session=self.session).first()
        self.assertIn("not found", call_1.result_payload)

        # Step B: AI corrects and asks for real.txt
        mock_instance.chat.return_value = {
            "content": ":::ai_read_file(path='real.txt') :::"
        }
        self.engine.tick(self.session.id)

        call_2 = ToolCall.objects.filter(
            turn__session=self.session).order_by('-created').first()
        self.assertIn("CONTENT_ALPHA", call_2.result_payload)

    @patch('talos_reasoning.engine.OllamaClient')
    def test_tool_safety_and_implicit_root(self, mock_client_cls):
        """
        Test 4: Tool Safety & Implicit Root - Verify jailbreak prevention.
        """
        mock_instance = mock_client_cls.return_value

        # AI tries to escape via ../
        mock_instance.chat.return_value = {
            "content": ":::ai_read_file(path='../secrets.txt') :::"
        }
        self.engine.tick(self.session.id)

        call = ToolCall.objects.filter(turn__session=self.session).first()
        self.assertIn("Access denied", call.result_payload)

    @patch('talos_reasoning.engine.OllamaClient')
    def test_live_sim_mocked(self, mock_client_cls):
        """
        Test 5: Live Simulation - Verify end-to-end relational flow.
        """
        mock_instance = mock_client_cls.return_value
        mock_instance.chat.return_value = {
            "content": "I need to list files.\n:::ai_list_files(path='.') :::",
            "tokens_input": 100,
            "tokens_output": 10,
            "model": "scout_light"
        }

        self.engine.tick(self.session.id)

        turn = self.session.turns.first()
        self.assertTrue(turn.tool_calls.exists())
        self.assertEqual(turn.tool_calls.first().tool.name, "ai_list_files")
        self.assertIn("real.txt", turn.tool_calls.first().result_payload)

    @patch('talos_reasoning.engine.OllamaClient')
    def test_empty_actions_no_crash(self, mock_client_cls):
        """Self-Correction Check: What if the AI just talks?"""
        mock_instance = mock_client_cls.return_value
        mock_instance.chat.return_value = {
            "content": "I am thinking but I have no tools for this."
        }

        # Should not raise exception
        self.engine.tick(self.session.id)
        turn = self.session.turns.first()
        self.assertFalse(turn.tool_calls.exists())
