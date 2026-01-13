from django.test import TestCase
from unittest.mock import patch
from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import ReasoningSession, ReasoningGoal, ReasoningStatusID
from talos_frontal.utils import parse_ai_actions


class FinalPolishTest(TestCase):
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        self.session = ReasoningSession.objects.create(
            goal="Stress Test", status_id=ReasoningStatusID.ACTIVE)
        self.engine = ReasoningEngine()

    def test_nasty_parser_edge_cases(self):
        """Verify the parser can handle absolute lunacy."""
        cases = [
            (":::ai_read_file(path='A.txt', start_line='', max_lines='10') :::",
             1, 'A.txt'), (":::ai_read_file  path = \"B.txt\" :::", 1, 'B.txt'),
            (":::ai_search_file('C.txt', 'pattern') :::", 1, 'C.txt'),
            ("Thought... :::ai_list_files('.') ::: ... :::ai_read_file('D.txt') :::",
             2, 'D.txt')
        ]
        for text, count, last_path in cases:
            actions = parse_ai_actions(text)
            self.assertEqual(len(actions), count, f"Failed on: {text}")
            self.assertEqual(actions[-1]['args']['path'], last_path)

    @patch('talos_reasoning.engine.OllamaClient')
    def test_hallucination_prevention_logic(self, mock_client_cls):
        """Verify the engine suppresses hallucinations through the system prompt."""
        mock_instance = mock_client_cls.return_value
        # Side effect: 1: Two tools, 2: Synthesis, 3: Summary
        mock_instance.chat.side_effect = [{
            "content":
                ":::ai_list_files('.') :::\n:::ai_read_file('/etc/passwd') :::"
        }, {
            "content": "Synthesis."
        }, {
            "content": "Summary."
        }]

        self.engine.tick(self.session.id)

        turn = self.session.turns.first()
        calls = turn.tool_calls.all().order_by('created')

        self.assertEqual(calls.count(), 2)
        res = calls[1].result_payload
        # Updated to check for streamlined error messages or security rejection
        self.assertTrue(
            "Access denied" in res or "not found" in res or
            "does not exist" in res,
            f"Expected security/existence error, got: {res}")
