from django.test import TestCase
from unittest.mock import patch
from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import (ReasoningSession, ReasoningGoal,
                                    ReasoningStatusID, ReasoningTurn)


class ContextIsolationTest(TestCase):
    """Verifies that raw history is isolated and summaries are used instead."""
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        self.session = ReasoningSession.objects.create(
            goal="Analyze Project",
            status_id=ReasoningStatusID.ACTIVE,
            rolling_context_summary="PREVIOUS_SUMMARY_DATA")
        self.engine = ReasoningEngine()

    @patch('talos_reasoning.engine.OllamaClient')
    def test_lobotomy_protocol(self, mock_client_cls):
        """
        Verify that raw history from Goal A is NOT in the prompt for Goal B.
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

        # Side effect: 1: Goal B Thought, 2: Goal B Summary
        mock_instance.chat.side_effect = [{
            "content": "Thinking about Goal B."
        }, {
            "content": "Summary B."
        }]

        # 3. Tick
        self.engine.tick(self.session.id)

        # 4. Verify Prompt (The first call was the tick inference)
        args, kwargs = mock_instance.chat.call_args_list[0]
        user_content = args[1]

        self.assertIn("Goal B", user_content)
        self.assertIn("PREVIOUS_SUMMARY_DATA", user_content)
        self.assertNotIn("SECRET_HISTORY_A", user_content)
