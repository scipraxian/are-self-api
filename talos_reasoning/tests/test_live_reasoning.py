import pytest
from django.test import TestCase
from django.conf import settings
from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import ReasoningSession, ReasoningGoal, ReasoningStatusID
from talos_parietal.synapse import OllamaClient


@pytest.mark.django_db
class LiveReasoningTest(TestCase):
    """
    REAL FIRE TESTS.
    Requires Ollama running on localhost:11434.
    """
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        # Verify Ollama is reachable before wasting time
        client = OllamaClient("llama3.2:3b")
        try:
            # Simple heartbeat
            client.chat("System", "Ping")
        except Exception:
            pytest.skip("Ollama not reachable on localhost:11434")

    def test_verify_ai_obeys_command(self):
        """
        The "Read manage.py" Test.
        We force the Engine to tick with a real model.
        We assert the AI actually tries to read the file we asked for.
        """
        # 1. Setup Session
        session = ReasoningSession.objects.create(
            goal="Live Verification",
            status_id=ReasoningStatusID.ACTIVE
        )

        # 2. Inject YOUR exact command
        ReasoningGoal.objects.create(
            session=session,
            reasoning_prompt="Read manage.py",
            status_id=ReasoningStatusID.PENDING
        )

        # 3. Run Engine (Real AI)
        engine = ReasoningEngine()
        engine.tick(session.id)

        # 4. Check Result
        session.refresh_from_db()
        last_turn = session.turns.last()

        # DEBUG: Print exactly what the AI thought
        print(f"\n[AI THOUGHT]:\n{last_turn.thought_process}\n")

        # 5. Assertions
        # Did it hallucinate Config.ini?
        if "Config/Default.ini" in last_turn.thought_process:
            self.fail("AI Hallucinated 'Config/Default.ini' instead of obeying instruction.")

        # Did it try to read manage.py?
        # We check the ToolCall arguments
        tool_call = last_turn.tool_calls.first()
        self.assertIsNotNone(tool_call, "AI did not call any tool.")

        print(f"[TOOL ARGS]: {tool_call.arguments}")

        self.assertIn("manage.py", tool_call.arguments,
                      f"AI ignored 'manage.py' instruction. Args: {tool_call.arguments}")

        # 6. Did the tool succeed?
        # If the file exists, the payload should contain 'import' or 'django'
        print(f"[TOOL RESULT]: {tool_call.result_payload[:100]}...")
        self.assertIn("django", tool_call.result_payload.lower())