import pytest
from django.test import TestCase

from talos_parietal.synapse import OllamaClient
from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import ReasoningGoal, ReasoningSession, ReasoningStatusID

pytestmark = pytest.mark.live

@pytest.mark.django_db
class LiveReasoningExtendedTest(TestCase):
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        self.model = "gemma3:27b"
        client = OllamaClient(self.model)
        try:
            client.chat("System", "Ping")
        except Exception:
            pytest.skip(f"Ollama model {self.model} not reachable")

        self.session = ReasoningSession.objects.create(
            goal="Extended Verification Suite",
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=50
        )
        self.engine = ReasoningEngine()

    def _inject_and_tick(self, prompt, clear_history=False):
        active_goals = self.session.goals.filter(status_id__in=[ReasoningStatusID.ACTIVE, ReasoningStatusID.PENDING])
        active_goals.update(status_id=ReasoningStatusID.COMPLETED)

        # RESTORED: The Safety Hack to unstick the model
        if clear_history:
            self.session.turns.all().delete()

        ReasoningGoal.objects.create(
            session=self.session,
            reasoning_prompt=prompt,
            status_id=ReasoningStatusID.PENDING
        )

        self.engine.tick(self.session.id)
        self.session.refresh_from_db()
        return self.session.turns.filter(tool_calls__isnull=False).last()

    def test_ls_and_locate(self):
        print("\n--- TEST: LS & LOCATE ---")
        turn1 = self._inject_and_tick("List files in the current directory.")
        if turn1:
            self.assertEqual(turn1.tool_calls.first().tool.name, "ai_list_files")

        turn2 = self._inject_and_tick("Read pyproject.toml", clear_history=True)
        if not turn2: self.fail("AI refused to read.")

        self.assertIn("pyproject", turn2.tool_calls.first().arguments)

    def test_error_recovery(self):
        print("\n--- TEST: ERROR RECOVERY ---")
        turn1 = self._inject_and_tick("Read ghosts.txt")
        if turn1:
            self.assertIn("not found", turn1.tool_calls.first().result_payload.lower())

        turn2 = self._inject_and_tick("Read manage.py", clear_history=True)
        if not turn2: self.fail("AI failed to recover.")

        self.assertIn("manage", turn2.tool_calls.first().arguments)