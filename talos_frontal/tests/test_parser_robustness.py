from django.test import SimpleTestCase
from talos_frontal.utils import parse_ai_actions

class ParserRobustnessTest(SimpleTestCase):

    def test_standard_format(self):
        """Standard Python syntax: :::tool(arg="val") :::"""
        text = ':::ai_read_file(path="A") :::'
        actions = parse_ai_actions(text)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['tool'], 'ai_read_file')
        self.assertEqual(actions[0]['args']['path'], 'A')

    def test_drifted_format(self):
        """Lazy syntax: :::tool('A')"""
        text = ":::ai_read_file('config.ini')" # Missing closing :::
        actions = parse_ai_actions(text)
        
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['tool'], 'ai_read_file')
        # Positional 'config.ini' mapped to 'path'
        self.assertEqual(actions[0]['args']['path'], 'config.ini')

    def test_mixed_bag(self):
        """Multiple calls in one thought."""
        text = """
        I will read:
        :::ai_read_file('A') :::
        Then search:
        :::ai_search_file(path='B', pattern='foo') :::
        """
        actions = parse_ai_actions(text)
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]['args']['path'], 'A')
        self.assertEqual(actions[1]['args']['pattern'], 'foo')