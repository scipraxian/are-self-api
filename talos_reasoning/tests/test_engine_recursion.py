import json
from django.test import TestCase
from unittest.mock import patch, MagicMock
from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import (ReasoningSession, ReasoningGoal,
                                    ReasoningStatusID, ToolDefinition)


class EngineRecursionTest(TestCase):
    """Verifies that the ReasoningEngine handles recursive ticks and safety limits."""
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        self.session = ReasoningSession.objects.create(
            goal="Test Recursion",
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=3)
        self.engine = ReasoningEngine()

    @patch('talos_reasoning.engine.OllamaClient')
    def test_recursive_tick_flow(self, mock_client_cls):
        """
        Verify that a tool call triggers a second tick automatically.
        AI 1: :::ai_list_files('.') :::
        AI 2: I am finished.
        Summary Call follows.
        """
        mock_instance = mock_client_cls.return_value

        # Responses: 1: Tool, 2: Synthesis, 3: Summary
        mock_instance.chat.side_effect = [{
            "content":
                "THOUGHT: I should list files.\n:::ai_list_files(path='.') :::"
        }, {
            "content": "THOUGHT: I see the files. I am done."
        }, {
            "content": "Summary result."
        }]

        # Trigger tick
        self.engine.tick(self.session.id)

        self.session.refresh_from_db()
        # Should have 2 turns
        self.assertEqual(self.session.turns.count(), 2)

        # Goal should be COMPLETED
        self.assertFalse(
            self.session.goals.filter(
                status_id=ReasoningStatusID.ACTIVE).exists())
        self.assertTrue(
            self.session.goals.filter(
                status_id=ReasoningStatusID.COMPLETED).exists())

        # Summary should be updated
        self.assertIn("Summary result", self.session.rolling_context_summary)

    @patch('talos_reasoning.engine.OllamaClient')
    def test_max_turns_safety(self, mock_client_cls):
        """Verify that the engine stops and marks MAXED_OUT after limit."""
        mock_instance = mock_client_cls.return_value

        # Fill responses for 3 turns (Varying paths to bypass loop guard)
        mock_instance.chat.side_effect = [
            {
                "content": ":::ai_list_files('a') :::"
            },  # Turn 1
            {
                "content": ":::ai_list_files('b') :::"
            },  # Turn 2
            {
                "content": ":::ai_list_files('c') :::"
            },  # Turn 3
        ]

        # Session max_turns is 3
        self.engine.tick(self.session.id)

        self.session.refresh_from_db()
        self.assertEqual(self.session.status_id, ReasoningStatusID.MAXED_OUT)
        self.assertEqual(self.session.turns.count(), 3)

    @patch('talos_reasoning.engine.OllamaClient')
    def test_loop_guard_activation(self, mock_client_cls):
        """Verify the loop guard stops repeating tools."""
        mock_instance = mock_client_cls.return_value

        # Two identical calls
        mock_instance.chat.side_effect = [
            {
                "content": ":::ai_list_files('.') :::"
            },  # Turn 1
            {
                "content": ":::ai_list_files('.') :::"
            },  # Turn 2 (Guard should trigger here)
        ]

        self.engine.tick(self.session.id)

        self.session.refresh_from_db()
        self.assertEqual(self.session.status_id,
                         ReasoningStatusID.ATTENTION_REQUIRED)
        self.assertEqual(self.session.turns.count(), 2)

        last_turn = self.session.turns.last()
        self.assertIn("Check the history", last_turn.thought_process)
