from django.test import TestCase
from unittest.mock import patch, MagicMock
from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import ReasoningSession, ReasoningGoal, ReasoningStatusID
from django.conf import settings


class EngineSimulationTest(TestCase):
    """
    Simulates the Chat -> Engine -> Tool loop.
    """
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        # 1. Setup Session (Manual Sandbox)
        self.session = ReasoningSession.objects.create(
            goal="Test Sandbox",
            status_id=ReasoningStatusID.ACTIVE
        )
        self.engine = ReasoningEngine()

    @patch('talos_reasoning.engine.OllamaClient')
    def test_chat_scenario_read_manage_py(self, mock_client_cls):
        """
        Scenario: User says 'Read manage.py'.
        We MOCK the AI correctly understanding this.
        We VERIFY the Engine executes it against the REAL disk.
        """
        # 1. Inject User Command
        ReasoningGoal.objects.create(
            session=self.session,
            reasoning_prompt="Read manage.py",
            status_id=ReasoningStatusID.PENDING
        )

        # 2. Mock AI Response (The Happy Path)
        mock_instance = mock_client_cls.return_value
        mock_instance.chat.return_value = {
            "content": "I will read the file.\n:::ai_read_file(path='manage.py') :::",
            "tokens_input": 10, "tokens_output": 10, "model": "scout_light"
        }

        # 3. Tick Engine
        self.engine.tick(self.session.id)

        # 4. Verify Result
        self.session.refresh_from_db()
        last_turn = self.session.turns.last()
        self.assertIsNotNone(last_turn)

        tool_call = last_turn.tool_calls.first()
        self.assertIsNotNone(tool_call)

        # PROOF: Did it read the actual file on your hard drive?
        # Since we are in Manual Mode, root_path = settings.BASE_DIR
        print(f"\n[TEST OUTPUT] Tool Result: {tool_call.result_payload[:100]}...")

        self.assertIn("django", tool_call.result_payload.lower())
        self.assertEqual(tool_call.status.name, "Completed")

    @patch('talos_reasoning.engine.OllamaClient')
    def test_chat_scenario_hallucination(self, mock_client_cls):
        """
        Scenario: User says 'Read manage.py'.
        We MOCK the AI Hallucinating 'Config/Default.ini' (Your Bug).
        We VERIFY the System catches the error gracefully.
        """
        ReasoningGoal.objects.create(
            session=self.session,
            reasoning_prompt="Read manage.py",
            status_id=ReasoningStatusID.PENDING
        )

        # 2. Mock AI Response (The Failure Path you saw)
        mock_instance = mock_client_cls.return_value
        mock_instance.chat.return_value = {
            "content": "Checking config...\n:::ai_read_file(path='Config/Default.ini') :::"
        }

        # 3. Tick
        self.engine.tick(self.session.id)

        # 4. Verify
        last_turn = self.session.turns.last()
        tool_call = last_turn.tool_calls.first()

        # It should have executed, but returned an Error string
        self.assertIn("Error: File 'Config/Default.ini' not found", tool_call.result_payload)
        # Status should technically be COMPLETED (The tool ran), but the payload describes failure.
        # Or if tool raised Exception, status is ERROR.
        # tools.py returns a string "Error: ...", so status is COMPLETED.
        self.assertEqual(tool_call.status.name, "Completed")