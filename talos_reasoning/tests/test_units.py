import os
import shutil
import tempfile
from django.test import SimpleTestCase, TestCase
from talos_frontal.utils import parse_ai_actions
from talos_parietal.tools import _resolve_path, ai_read_file

class ParserTest(SimpleTestCase):
    """
    Verifies the system can read the AI's messy handwriting.
    """
    def test_parser_standard_kwargs(self):
        # The ideal case
        text = ':::ai_read_file(path="manage.py") :::'
        actions = parse_ai_actions(text)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['args']['path'], 'manage.py')

    def test_parser_lazy_positional(self):
        # The "Lazy AI" case (ls .)
        text = ":::ai_list_files('.') :::"
        actions = parse_ai_actions(text)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['tool'], 'ai_list_files')
        self.assertEqual(actions[0]['args']['path'], '.')

    def test_parser_json_fallback(self):
        # The "Legacy" case
        text = ':::ACTION {"tool": "ai_read_file", "args": {"path": "manage.py"}} :::'
        actions = parse_ai_actions(text)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['args']['path'], 'manage.py')


class PathResolverTest(TestCase):
    """
    Verifies the Virtual Filesystem logic prevents jailbreaks and finds files.
    """
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.secret_file = os.path.join(self.temp_dir, "manage.py")
        with open(self.secret_file, 'w') as f:
            f.write("import django")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_resolve_relative_path(self):
        """Standard usage: 'manage.py' -> 'C:/Root/manage.py'"""
        resolved, error = _resolve_path("manage.py", root_path=self.temp_dir)
        self.assertIsNone(error)
        self.assertEqual(resolved, self.secret_file)

    def test_resolve_jailbreak_attempt(self):
        """Malicious usage: '../windows/system32'"""
        resolved, error = _resolve_path("../secrets.txt", root_path=self.temp_dir)
        self.assertIsNotNone(error)
        self.assertIn("Access denied", error)

    def test_tool_read_success(self):
        """Does ai_read_file actually return content?"""
        result = ai_read_file("manage.py", root_path=self.temp_dir)
        self.assertIn("1: import django", result)