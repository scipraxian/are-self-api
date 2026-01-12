from django.test import SimpleTestCase

from talos_frontal.utils import parse_ai_actions


class ParserRobustnessTest(SimpleTestCase):

    def test_standard_format(self):
        """The Happy Path: :::ACTION {tool...} :::"""
        text = ':::ACTION {"tool": "ai_read_file", "args": {"path": "A"}} :::'
        actions = parse_ai_actions(text)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['tool'], 'ai_read_file')
        self.assertEqual(actions[0]['args']['path'], 'A')

    def test_drifted_format_tag_is_tool(self):
        """The Fix: :::ai_read_file {args...} :::"""
        # This is exactly what broke your system
        text = ':::ai_read_file {"path": "Config/DefaultEngine.ini"} :::'
        actions = parse_ai_actions(text)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['tool'], 'ai_read_file')
        # In drifted format, the payload IS the args
        self.assertEqual(actions[0]['args']['path'], 'Config/DefaultEngine.ini')

    def test_mixed_bag(self):
        """AI gets confused and uses both formats."""
        text = """
        I will read the file:
        :::ai_read_file {"path": "A"} :::
        And then execute:
        :::ACTION {"tool": "ai_execute_task", "args": {"head_id": "B"}} :::
        """
        actions = parse_ai_actions(text)
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]['tool'], 'ai_read_file')
        self.assertEqual(actions[1]['tool'], 'ai_execute_task')

    def test_json_cleanup(self):
        """Ensure regex captures multiline JSON correctly."""
        text = """
        :::ai_read_file {
            "path": "A"
        } :::
        """
        actions = parse_ai_actions(text)
        self.assertEqual(actions[0]['args']['path'], 'A')
