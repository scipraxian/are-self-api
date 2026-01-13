import pytest
import json
from django.test import TestCase
from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import ReasoningSession, ReasoningGoal, ReasoningStatusID
from talos_parietal.synapse import OllamaClient


@pytest.mark.django_db
class LiveReasoningExtendedTest(TestCase):
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        client = OllamaClient("llama3.2:3b")
        try:
            client.chat("System", "Ping")
        except Exception:
            pytest.skip("Ollama not reachable")

        self.session = ReasoningSession.objects.create(
            goal="Extended Verification Suite",
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=50
        )
        self.engine = ReasoningEngine()

    def _inject_and_tick(self, prompt):
        active_goals = self.session.goals.filter(status_id__in=[ReasoningStatusID.ACTIVE, ReasoningStatusID.PENDING])
        active_goals.update(status_id=ReasoningStatusID.COMPLETED)

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
            call1 = turn1.tool_calls.first()
            self.assertEqual(call1.tool.name, "ai_list_files")

        target_file = "pyproject.toml"
        # UPDATED PROMPT: More forceful to prevent "List loop"
        turn2 = self._inject_and_tick(f"URGENT: READ_FILE: {target_file}")

        if not turn2:
            self.fail("AI refused to read file.")

        call2 = turn2.tool_calls.first()
        self.assertIn("pyproject", call2.arguments)

    def test_error_recovery(self):
        print("\n--- TEST: ERROR RECOVERY ---")
        # 1. Force Fail
        turn1 = self._inject_and_tick("Read ghosts.txt")
        if turn1:
            call1 = turn1.tool_calls.first()
            self.assertIn("not found", call1.result_payload.lower())

        # 2. Recover
        turn2 = self._inject_and_tick("Read manage.py")
        if not turn2:
            self.fail("AI failed to recover.")

        call2 = turn2.tool_calls.first()
        self.assertIn("manage", call2.arguments)