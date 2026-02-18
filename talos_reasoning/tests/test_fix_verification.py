from unittest.mock import MagicMock, patch

from django.test import TestCase

from talos_parietal.models import ToolDefinition
from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import (
    ReasoningGoal,
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)


class GoalSwitchingTest(TestCase):
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        self.session = ReasoningSession.objects.create(
            goal="Loop Test",
            status_id=ReasoningStatusID.ACTIVE
        )
        self.engine = ReasoningEngine()

    def test_goal_preemption(self):
        # 1. Start Goal A
        goal_a = ReasoningGoal.objects.create(
            session=self.session,
            reasoning_prompt="Task A",
            status_id=ReasoningStatusID.ACTIVE
        )

        # 2. Inject Goal B
        goal_b = ReasoningGoal.objects.create(
            session=self.session,
            reasoning_prompt="Task B",
            status_id=ReasoningStatusID.PENDING
        )

        # 3. Tick
        with patch('talos_reasoning.engine.OllamaClient') as mock_client:
            mock_client.return_value.chat.side_effect = [
                {"content": "Doing B"},
                {"content": "Summary B"}
            ]
            self.engine.tick(self.session.id)

        # 4. Assertions
        goal_a.refresh_from_db()
        goal_b.refresh_from_db()

        self.assertEqual(goal_a.status.name, "Completed")
        self.assertEqual(goal_b.status.name, "Completed")

    def test_context_continuity(self):
        """
        Verify that turns from Goal A DO appear in the prompt for Goal B.
        (Unified Consciousness)
        """
        # 1. Create History for Goal A
        goal_a = ReasoningGoal.objects.create(
            session=self.session, reasoning_prompt="Read manage.py", status_id=ReasoningStatusID.COMPLETED
        )
        ReasoningTurn.objects.create(
            session=self.session, active_goal=goal_a, turn_number=1,
            thought_process="I read manage.py"
        )

        # 2. Create Goal B (Pending)
        goal_b = ReasoningGoal.objects.create(
            session=self.session, reasoning_prompt="Read requirements.txt", status_id=ReasoningStatusID.PENDING
        )

        # 3. Tick & Capture Prompt
        with patch('talos_reasoning.engine.OllamaClient') as mock_client:
            mock_instance = mock_client.return_value
            mock_instance.chat.side_effect = [{"content": "Ok, reading requirements."}]

            self.engine.tick(self.session.id)

            # Get args
            if mock_instance.chat.call_args_list:
                call_args = mock_instance.chat.call_args_list[0]
                prompt_content = call_args[0][1]  # user_content
            else:
                self.fail("Ollama was not called.")

            # 4. Verify Continuity (History IS present)
            self.assertIn("requirements.txt", prompt_content)
            self.assertIn("manage.py", prompt_content, "Context Amnesia! Old history missing.")