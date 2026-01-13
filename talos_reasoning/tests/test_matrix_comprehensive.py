import pytest
import os
import shutil
import tempfile
from django.test import TestCase, SimpleTestCase
from talos_frontal.utils import parse_command_string
from talos_parietal.tools import _resolve_path


class ParserMatrixTest(SimpleTestCase):
    def assert_action(self, text, tool, arg_key, arg_val):
        action = parse_command_string(text)
        self.assertIsNotNone(action, f"Failed to parse: {text}")
        self.assertEqual(action['tool'], tool)
        self.assertEqual(str(action['args'].get(arg_key)), str(arg_val))

    def test_syntax_variations(self):
        """Verify the parser handles the new CLI syntax."""
        matrix = [
            ('READ_FILE: A', 'ai_read_file', 'path', 'A'),
            ('SEARCH_FILE: logs.txt "error"', 'ai_search_file', 'pattern', 'error'),
            ('LIST_DIR: .', 'ai_list_files', 'path', '.'),
            ('Thinking...\nREAD_FILE: config.ini', 'ai_read_file', 'path', 'config.ini')
        ]
        for text, tool, key, val in matrix:
            with self.subTest(text=text):
                self.assert_action(text, tool, key, val)


class ToolSafetyMatrixTest(TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.safe_file = os.path.join(self.root, "safe.txt")
        with open(self.safe_file, 'w') as f:
            f.write("safe")

        # Create a file OUTSIDE the root
        self.outside_root = tempfile.mkdtemp()
        self.secret_file = os.path.join(self.outside_root, "secret.txt")
        with open(self.secret_file, 'w') as f:
            f.write("secret")

    def tearDown(self):
        shutil.rmtree(self.root)
        shutil.rmtree(self.outside_root)

    def test_path_resolution_matrix(self):
        """Verify the Jail is secure, BUT allows absolute overrides."""
        scenarios = [
            ("safe.txt", self.safe_file, None),
            ("./safe.txt", self.safe_file, None),
            ("subdir/../safe.txt", self.safe_file, None),
            ("../secret.txt", None, "Access denied"),
            # UPDATED: Absolute path should SUCCEED now (return path, no error)
            (self.secret_file, self.secret_file, None),
        ]

        for input_path, expected, err_fragment in scenarios:
            with self.subTest(path=input_path):
                path, error = _resolve_path(input_path, self.root)

                if err_fragment:
                    self.assertIsNone(path)
                    self.assertTrue("Access denied" in error or "outside" in error)
                else:
                    self.assertIsNone(error)
                    self.assertEqual(path, expected)