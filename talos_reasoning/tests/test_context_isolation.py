from django.test import TestCase
from unittest.mock import patch
from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import (ReasoningSession, ReasoningGoal,
                                    ReasoningStatusID, ReasoningTurn)


class ContextContinuityTest(TestCase):
    """Verifies that the AI retains context across different goals (Unified Consciousness)."""
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        self.session = ReasoningSession.objects.create(
            goal="Analyze Project",
            status_id=ReasoningStatusID.ACTIVE,
            rolling_context_summary="PREVIOUS_SUMMARY_DATA")
        self.engine = ReasoningEngine()

    @patch('talos_reasoning.engine.OllamaClient')
    def test_context_continuity(self, mock_client_cls):
        """
        Verify that history from Goal A **IS** present in the prompt for Goal B.
        This ensures the AI can answer follow-up questions about previous actions.
        """
        mock_instance = mock_client_cls.return_value

        # 1. Complete Goal A
        goal_a = ReasoningGoal.objects.create(
            session=self.session,
            reasoning_prompt="Goal A",
            status_id=ReasoningStatusID.COMPLETED)

        ReasoningTurn.objects.create(session=self.session,
                                     active_goal=goal_a,
                                     turn_number=1,
                                     input_context_snapshot="...",
                                     thought_process="SECRET_HISTORY_A")

        # 2. Start Goal B
        ReasoningGoal.objects.create(session=self.session,
                                     reasoning_prompt="Goal B",
                                     status_id=ReasoningStatusID.PENDING)

        # Side effect: 1: Goal B Thought
        mock_instance.chat.return_value = {
            "content": "Thinking about Goal B."
        }

        # 3. Tick
        self.engine.tick(self.session.id)

        # 4. Verify Prompt
        args, kwargs = mock_instance.chat.call_args_list[0]
        user_content = args[1]

        self.assertIn("Goal B", user_content)

        # CHANGED: We now EXPECT the history to be visible
        self.assertIn("SECRET_HISTORY_A", user_content, "Context Amnesia detected! Old history missing.")

        # Summary should also be there
        self.assertIn("PREVIOUS_SUMMARY_DATA", user_content)