from django.test import TestCase
from unittest.mock import patch
from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import ReasoningSession, ReasoningGoal, ReasoningStatusID
from django.conf import settings


class EngineSimulationTest(TestCase):
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        self.session = ReasoningSession.objects.create(
            goal="Test Sandbox", status_id=ReasoningStatusID.ACTIVE
        )
        self.engine = ReasoningEngine()

    @patch('talos_reasoning.engine.OllamaClient')
    def test_chat_scenario_read_manage_py(self, mock_client_cls):
        # 1. Inject User Command
        ReasoningGoal.objects.create(
            session=self.session, reasoning_prompt="Read manage.py", status_id=ReasoningStatusID.PENDING
        )

        # 2. Mock AI Response
        mock_instance = mock_client_cls.return_value
        mock_instance.chat.return_value = {
            "content": ":::ai_read_file(path='manage.py') :::",
            "tokens_input": 10, "tokens_output": 10, "model": "scout_light"
        }

        # 3. Tick
        self.engine.tick(self.session.id)

        # 4. Verify
        self.session.refresh_from_db()
        last_turn = self.session.turns.last()
        tool_call = last_turn.tool_calls.first()

        self.assertIn("django", tool_call.result_payload.lower())
        self.assertEqual(tool_call.status.name, "Completed")

    @patch('talos_reasoning.engine.OllamaClient')
    def test_chat_scenario_hallucination(self, mock_client_cls):
        ReasoningGoal.objects.create(
            session=self.session, reasoning_prompt="Read manage.py", status_id=ReasoningStatusID.PENDING
        )

        # 2. Mock AI Hallucination
        mock_instance = mock_client_cls.return_value
        mock_instance.chat.return_value = {
            "content": ":::ai_read_file(path='Config/Default.ini') :::"
        }

        # 3. Tick
        self.engine.tick(self.session.id)

        # 4. Verify
        last_turn = self.session.turns.last()
        tool_call = last_turn.tool_calls.first()

        # FIX: Matched string to tools.py output (Path vs File)
        self.assertIn("Error: Path 'Config/Default.ini' not found", tool_call.result_payload)
        self.assertEqual(tool_call.status.name, "Completed")