import pytest
import os
import json
import tempfile
import shutil
from django.test import TestCase, SimpleTestCase
from unittest.mock import patch, MagicMock
from talos_frontal.utils import parse_ai_actions
from talos_parietal.tools import _resolve_path, ai_read_file
from talos_reasoning.models import ReasoningSession, ReasoningGoal, ReasoningStatusID
from talos_reasoning.engine import ReasoningEngine


# ==========================================
# 1. PARSER STRESS MATRIX
# ==========================================
class ParserMatrixTest(SimpleTestCase):
    def assert_action(self, text, tool, arg_key, arg_val):
        actions = parse_ai_actions(text)
        self.assertTrue(len(actions) > 0, f"Failed to parse: {text}")
        self.assertEqual(actions[0]['tool'], tool)
        self.assertEqual(str(actions[0]['args'].get(arg_key)), str(arg_val))

    def test_syntax_variations(self):
        """Verify the parser handles every weird way an LLM might write."""
        matrix = [
            (':::ai_read_file(path="A") :::', 'ai_read_file', 'path', 'A'),
            (':::ai_read_file(path="A"):::', 'ai_read_file', 'path', 'A'),  # No space
            ('::: ai_read_file ( path = "A" ) :::', 'ai_read_file', 'path', 'A'),  # Spaced
            (':::ai_read_file(\'A\') :::', 'ai_read_file', 'path', 'A'),  # Positional Single Quote
            (':::ai_read_file("A") :::', 'ai_read_file', 'path', 'A'),  # Positional Double Quote
            (':::ACTION {"tool": "ai_read_file", "args": {"path": "A"}} :::', 'ai_read_file', 'path', 'A'),  # JSON
            (':::ai_read_file {"path": "A"} :::', 'ai_read_file', 'path', 'A'),  # Drifted JSON
            # Lazy / EOF cases
            (':::ai_read_file(path="A")', 'ai_read_file', 'path', 'A'),
        ]
        for text, tool, key, val in matrix:
            with self.subTest(text=text):
                self.assert_action(text, tool, key, val)


# ==========================================
# 2. TOOL SAFETY MATRIX
# ==========================================
class ToolSafetyMatrixTest(TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.safe_file = os.path.join(self.root, "safe.txt")
        with open(self.safe_file, 'w') as f: f.write("safe")

        # Create a file OUTSIDE the root
        self.outside_root = tempfile.mkdtemp()
        self.secret_file = os.path.join(self.outside_root, "secret.txt")
        with open(self.secret_file, 'w') as f: f.write("secret")

    def tearDown(self):
        shutil.rmtree(self.root)
        shutil.rmtree(self.outside_root)

    def test_path_resolution_matrix(self):
        """Verify the Jail is secure, BUT allows absolute overrides."""
        scenarios = [
            ("safe.txt", self.safe_file, None),  # Standard
            ("./safe.txt", self.safe_file, None),  # Dot prefix
            ("subdir/../safe.txt", self.safe_file, None),  # Traversal internal
            ("../secret.txt", None, "Access denied"),  # Jailbreak relative (BLOCKED)

            # ABSOLUTE PATH -> ALLOWED (User Requirement: "Any file anywhere")
            (self.secret_file, self.secret_file, None),
        ]

        for input_path, expected, err_fragment in scenarios:
            with self.subTest(path=input_path):
                path, error = _resolve_path(input_path, self.root)

                if err_fragment:
                    self.assertIsNone(path, f"Path should be None for jailbreak: {input_path}")
                    self.assertIsNotNone(error, f"Error should be returned for: {input_path}")
                    self.assertIn(err_fragment, error)
                else:
                    self.assertIsNone(error)
                    self.assertEqual(path, expected)


# ==========================================
# 3. ENGINE STATE & INTERRUPT TEST
# ==========================================
class EngineLogicTest(TestCase):
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        self.session = ReasoningSession.objects.create(
            goal="Logic Test",
            status_id=ReasoningStatusID.ACTIVE
        )
        self.engine = ReasoningEngine()

    def test_interrupt_logic(self):
        """
        Verify that injecting a new goal effectively
        stops the Engine from caring about the old goal.
        """
        # 1. Goal A (Active)
        g1 = ReasoningGoal.objects.create(session=self.session, reasoning_prompt="Goal A",
                                          status_id=ReasoningStatusID.ACTIVE)

        # 2. Inject Goal B (Pending) - Simulate Chat Override
        # NOTE: This mimics the logic we added to views.py
        g1.status_id = ReasoningStatusID.COMPLETED
        g1.save()

        g2 = ReasoningGoal.objects.create(session=self.session, reasoning_prompt="Goal B",
                                          status_id=ReasoningStatusID.PENDING)

        # 3. Tick
        with patch('talos_reasoning.engine.OllamaClient') as mock_client:
            mock_client.return_value.chat.return_value = {"content": "Thinking about Goal B"}
            self.engine.tick(self.session.id)

        # 4. Verify Goal B was selected
        self.session.refresh_from_db()
        turn = self.session.turns.last()
        self.assertEqual(turn.active_goal, g2, "Engine failed to switch to new goal!")