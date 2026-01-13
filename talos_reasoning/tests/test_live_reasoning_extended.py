import pytest
from django.test import TestCase
from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import ReasoningSession, ReasoningGoal, ReasoningStatusID
from talos_parietal.synapse import OllamaClient


@pytest.mark.django_db
class LiveReasoningExtendedTest(TestCase):
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        # Verify connectivity first
        client = OllamaClient("llama3.2:3b")
        try:
            client.chat("System", "Ping")
        except Exception:
            pytest.skip("Ollama not reachable on localhost:11434")

        self.session = ReasoningSession.objects.create(
            goal="Extended Verification Suite",
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=50
        )
        self.engine = ReasoningEngine()

    def _inject_and_tick(self, prompt):
        """Helper to simulate user chatting."""

        # Retire old goals to force focus
        active_goals = self.session.goals.filter(
            status_id__in=[ReasoningStatusID.ACTIVE, ReasoningStatusID.PENDING]
        )
        active_goals.update(status_id=ReasoningStatusID.COMPLETED)

        # Create new goal
        ReasoningGoal.objects.create(
            session=self.session,
            reasoning_prompt=prompt,
            status_id=ReasoningStatusID.PENDING
        )

        # Tick
        self.engine.tick(self.session.id)

        # Refresh and fetch
        self.session.refresh_from_db()
        turn = self.session.turns.last()

        # Safety Check
        if turn is None:
            self.fail(f"Engine Tick produced NO TURN for prompt: '{prompt}'. Check Engine Logs.")

        return turn

    def test_sequential_commands_switching(self):
        print("\n--- TEST: SEQUENTIAL SWITCHING ---")

        # Turn 1
        turn1 = self._inject_and_tick("Read manage.py")
        call1 = turn1.tool_calls.first()
        self.assertIsNotNone(call1, "Turn 1 produced no tool calls")
        self.assertIn("manage.py", call1.arguments)

        # Turn 2
        turn2 = self._inject_and_tick("Read requirements.txt")
        call2 = turn2.tool_calls.first()
        self.assertIsNotNone(call2, "Turn 2 produced no tool calls")

        self.assertNotEqual(call1.arguments, call2.arguments)
        self.assertIn("requirements.txt", call2.arguments)

    def test_ls_and_locate(self):
        print("\n--- TEST: LS & LOCATE ---")
        turn1 = self._inject_and_tick("List files in the current directory.")
        call1 = turn1.tool_calls.first()
        self.assertIsNotNone(call1)
        self.assertEqual(call1.tool.name, "ai_list_files")

        target_file = "pyproject.toml"
        turn2 = self._inject_and_tick(f"Read the contents of {target_file}")
        call2 = turn2.tool_calls.first()
        self.assertIsNotNone(call2)

        self.assertIn(target_file, call2.arguments)

    def test_error_recovery(self):
        print("\n--- TEST: ERROR RECOVERY ---")

        # Turn 1: Fail
        turn1 = self._inject_and_tick("Read fake_ghost_file.txt")
        call1 = turn1.tool_calls.first()
        self.assertIsNotNone(call1)
        self.assertIn("not found", call1.result_payload)

        # Turn 2: Recover
        turn2 = self._inject_and_tick("Okay, read manage.py instead.")
        call2 = turn2.tool_calls.first()
        self.assertIsNotNone(call2)

        self.assertIn("manage.py", call2.arguments)
        self.assertIn("django", call2.result_payload.lower())

    def test_search_logic(self):
        print("\n--- TEST: SEARCH LOGIC ---")
        turn1 = self._inject_and_tick("Search for 'urlpatterns' in urls.py")
        call1 = turn1.tool_calls.first()
        self.assertIsNotNone(call1)

        self.assertEqual(call1.tool.name, "ai_search_file")
        self.assertIn("urlpatterns", call1.arguments)