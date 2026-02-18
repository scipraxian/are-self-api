from unittest.mock import patch

from django.test import TestCase

from talos_parietal.models import ToolDefinition
from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import (
    ReasoningGoal,
    ReasoningSession,
    ReasoningStatusID,
)


class EngineRefactorTest(TestCase):
    """Verifies the refactored modular and non-recursive engine logic."""
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        self.session = ReasoningSession.objects.create(
            goal="Test Refactor",
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=5)
        self.engine = ReasoningEngine()

    @patch('talos_reasoning.engine.OllamaClient')
    def test_single_tick_no_recursion(self, mock_client_cls):
        """Verify that a tool call DOES NOT trigger a second tick."""
        mock_instance = mock_client_cls.return_value
        # AI identifies a tool call
        mock_instance.chat.return_value = {"content": "LIST_DIR: ."}

        # Trigger tick
        self.engine.tick(self.session.id)

        self.session.refresh_from_db()
        # Should have exactly 1 turn, despite tool call
        self.assertEqual(self.session.turns.count(), 1)

        # Verify tool call record exists
        turn = self.session.turns.first()
        self.assertEqual(turn.tool_calls.count(), 1)
        self.assertEqual(turn.tool_calls.first().tool.name, 'ai_list_files')

    @patch('talos_reasoning.engine.OllamaClient')
    def test_synthesis_completes_goal(self, mock_client_cls):
        """Verify that a response without a command completes the goal."""
        mock_instance = mock_client_cls.return_value
        # AI provides a final answer
        mock_instance.chat.side_effect = [
            {
                "content": "I have found the answer correctly."
            },  # _query_brain
            {
                "content": "Summary of work."
            }  # _update_rolling_summary
        ]

        self.engine.tick(self.session.id)

        self.session.refresh_from_db()
        self.assertEqual(self.session.turns.count(), 1)

        # Goal should be COMPLETED
        active_goal = self.session.goals.first()
        self.assertEqual(active_goal.status_id, ReasoningStatusID.COMPLETED)

        # Summary should be updated
        self.assertIn("Summary of work", self.session.rolling_context_summary)

    @patch('talos_reasoning.engine.OllamaClient')
    def test_max_turns_enforcement(self, mock_client_cls):
        """Verify that the engine respects max_turns."""
        self.session.max_turns = 1
        self.session.save()

        # Create one turn already
        self.session.turns.create(active_goal=self.session.goals.create(
            status_id=ReasoningStatusID.ACTIVE),
                                  turn_number=1,
                                  status_id=ReasoningStatusID.COMPLETED)

        # Ticking should immediately hit the limit
        self.engine.tick(self.session.id)

        self.session.refresh_from_db()
        self.assertEqual(self.session.status_id, ReasoningStatusID.MAXED_OUT)
        # Still only 1 turn
        self.assertEqual(self.session.turns.count(), 1)
