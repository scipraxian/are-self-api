import pytest
import json
from django.test import TestCase
from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import ReasoningSession, ReasoningGoal, ReasoningStatusID
from talos_parietal.synapse import OllamaClient


@pytest.mark.django_db
class LiveReasoningTest(TestCase):
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        client = OllamaClient("llama3.2:3b")
        try:
            client.chat("System", "Ping")
        except Exception:
            pytest.skip("Ollama not reachable on localhost:11434")

    def test_verify_ai_obeys_command(self):
        """
        Verify the AI attempts to interact with 'manage.py'.
        We accept ai_read_file OR ai_search_file as valid first steps.
        """
        session = ReasoningSession.objects.create(
            goal="Live Verification",
            status_id=ReasoningStatusID.ACTIVE
        )

        ReasoningGoal.objects.create(
            session=session,
            reasoning_prompt="URGENT: Read the content of 'manage.py'.",
            status_id=ReasoningStatusID.PENDING
        )

        engine = ReasoningEngine()
        engine.tick(session.id)

        session.refresh_from_db()
        last_turn = session.turns.filter(tool_calls__isnull=False).last()

        if not last_turn:
            self.fail(f"AI produced no tool calls. Thoughts: {[t.thought_process for t in session.turns.all()]}")

        tool_call = last_turn.tool_calls.first()
        print(f"\n[TOOL]: {tool_call.tool.name} | ARGS: {tool_call.arguments}")

        # ROBUST ASSERTION: Parse JSON and check values loosely
        try:
            args = json.loads(tool_call.arguments)
            # Check if any value contains 'manage'
            found = any("manage" in str(v) for v in args.values())
            self.assertTrue(found, f"AI did not target 'manage.py'. Args: {args}")
        except json.JSONDecodeError:
            self.fail(f"AI produced invalid JSON args: {tool_call.arguments}")