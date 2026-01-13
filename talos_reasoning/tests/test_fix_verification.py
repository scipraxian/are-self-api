from django.test import TestCase
from unittest.mock import patch, MagicMock
from talos_reasoning.models import (
    ReasoningSession, ReasoningGoal, ReasoningTurn,
    ToolDefinition, ReasoningStatusID
)
from talos_reasoning.engine import ReasoningEngine


class GoalSwitchingTest(TestCase):
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        self.session = ReasoningSession.objects.create(
            goal="Loop Test",
            status_id=ReasoningStatusID.ACTIVE
        )
        self.engine = ReasoningEngine()

    def test_goal_preemption(self):
        """
        Verify that if Goal A is ACTIVE, adding Goal B (PENDING)
        causes the Engine to switch to Goal B immediately.
        """
        # 1. Start Goal A
        goal_a = ReasoningGoal.objects.create(
            session=self.session,
            reasoning_prompt="Task A",
            status_id=ReasoningStatusID.ACTIVE
        )

        # 2. Inject Goal B (Simulate User Chat)
        goal_b = ReasoningGoal.objects.create(
            session=self.session,
            reasoning_prompt="Task B",
            status_id=ReasoningStatusID.PENDING
        )

        # 3. Tick (Mock AI to ignore output, we only care about state transition)
        with patch('talos_reasoning.engine.OllamaClient') as mock_client:
            mock_client.return_value.chat.return_value = {"content": "Doing B"}
            self.engine.tick(self.session.id)

        # 4. Assertions
        goal_a.refresh_from_db()
        goal_b.refresh_from_db()

        self.assertEqual(goal_a.status.name, "Completed", "Old goal should be auto-completed by Engine.")
        self.assertEqual(goal_b.status.name, "Active", "New goal should be active.")

        # Verify the Turn is linked to Goal B
        turn = self.session.turns.last()
        self.assertEqual(turn.active_goal, goal_b)

    def test_context_isolation(self):
        """
        Verify that turns from Goal A do NOT appear in the prompt for Goal B.
        This prevents the 'Stuck Loop' hallucination.
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
            mock_instance.chat.return_value = {"content": "Ok"}

            self.engine.tick(self.session.id)

            # Get the args passed to chat()
            call_args = mock_instance.chat.call_args
            prompt_content = call_args[0][1]  # user_content

            print(f"\n[DEBUG] PROMPT SENT TO AI:\n{prompt_content}\n")

            # 4. Verify Isolation
            self.assertIn("requirements.txt", prompt_content, "Prompt must contain new goal")
            self.assertNotIn("manage.py", prompt_content, "Prompt must NOT contain old goal history")
            self.assertIn("(No history for this specific task. Start fresh.)", prompt_content)