import os
import shutil
import tempfile
from unittest.mock import patch
from django.test import TestCase

from talos_frontal.utils import parse_command_string
from talos_parietal.tools import ai_read_file, ai_execute_task, ai_search_file


class SpellcasterUtilsTest(TestCase):
    def test_parse_valid_action(self):
        text = """
        I need to check the config.
        READ_FILE: config.ini
        That should tell us more.
        """
        action = parse_command_string(text)
        self.assertIsNotNone(action)
        self.assertEqual(action['tool'], "ai_read_file")
        self.assertEqual(action['args']['path'], "config.ini")


class ToolTest(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.fpath = os.path.join(self.temp_dir, "test.txt")
        with open(self.fpath, "w") as f:
            f.write("Hello World\nLine 2\nLine 3")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_ai_read_file_read(self):
        content = ai_read_file("test.txt", root_path=self.temp_dir)
        self.assertIn("Hello World", content)

    def test_ai_read_file_traversal_attempt(self):
        result = ai_read_file("../outside.txt", root_path=self.temp_dir)
        self.assertIn("Access denied", result)

    def test_ai_search_file(self):
        result = ai_search_file("test.txt", "Line 2", root_path=self.temp_dir)
        self.assertIn("Match 1", result)
        self.assertIn("Line 2", result)

    @patch('talos_parietal.tools.cast_hydra_spell.delay')
    def test_cast_spell(self, mock_celery):
        valid_uuid = "00000000-0000-0000-0000-000000000000"
        result = ai_execute_task(valid_uuid)
        self.assertIn("Successfully queued", result)
        mock_celery.assert_called_with(valid_uuid)

    def test_ai_read_file_slicing(self):
        fpath = os.path.join(self.temp_dir, "long_file.txt")
        with open(fpath, "w") as f:
            for i in range(100):
                f.write(f"Line {i + 1}\n")

        content = ai_read_file("long_file.txt", root_path=self.temp_dir, start_line=10, max_lines=3)

        self.assertIn("10: Line 10", content)
        self.assertIn("11: Line 11", content)
        self.assertIn("12: Line 12", content)
        self.assertNotIn("13: Line 13", content)
        self.assertIn("Use start_line=13 to read more", content)