from django.test import TestCase
from talos_parietal.registry import ModelRegistry
from talos_frontal.utils import parse_command_string


class RefactorPhase12Test(TestCase):
    """Tests Phase 1 and 2 of the Reasoning Engine refactor."""

    def test_model_registry_constants(self):
        """Verify integer constants are correctly defined."""
        self.assertEqual(ModelRegistry.SCOUT_LIGHT, 1)
        self.assertEqual(ModelRegistry.COMMANDER, 2)

    def test_model_registry_get_model(self):
        """Verify model mapping and defaults."""
        self.assertEqual(ModelRegistry.get_model(ModelRegistry.SCOUT_LIGHT),
                         "llama3.2:3b")
        self.assertEqual(ModelRegistry.get_model(ModelRegistry.COMMANDER),
                         "gemma3:27b")
        # Test fallback to SCOUT_LIGHT
        self.assertEqual(ModelRegistry.get_model(999), "llama3.2:3b")

    def test_parse_command_read_file(self):
        """Verify READ_FILE syntax parsing with start line."""
        text = "Thinking... \nREAD_FILE: config.py 10\nSome other text"
        result = parse_command_string(text)
        self.assertEqual(result, {
            'tool': 'ai_read_file',
            'args': {
                'path': 'config.py',
                'start_line': 10
            }
        })

    def test_parse_command_read_file_no_start_line(self):
        """Verify READ_FILE syntax parsing defaults to start_line 1."""
        text = "READ_FILE: main.py"
        result = parse_command_string(text)
        self.assertEqual(result, {
            'tool': 'ai_read_file',
            'args': {
                'path': 'main.py',
                'start_line': 1
            }
        })

    def test_parse_command_search_file(self):
        """Verify SEARCH_FILE syntax parsing with quoted pattern."""
        text = 'SEARCH_FILE: logs.txt "error 404"'
        result = parse_command_string(text)
        self.assertEqual(
            result, {
                'tool': 'ai_search_file',
                'args': {
                    'path': 'logs.txt',
                    'pattern': 'error 404'
                }
            })

    def test_parse_command_list_dir(self):
        """Verify LIST_DIR syntax parsing."""
        text = "LIST_DIR: /home/user/project"
        result = parse_command_string(text)
        self.assertEqual(result, {
            'tool': 'ai_list_files',
            'args': {
                'path': '/home/user/project'
            }
        })

    def test_parse_command_none(self):
        """Verify that text without valid commands returns None."""
        text = "Just some random text without commands."
        result = parse_command_string(text)
        self.assertIsNone(result)
