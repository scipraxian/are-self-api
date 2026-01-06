#!/usr/bin/env python3
"""Unit tests for VersionStamper.py."""

import json
import os
import shutil
import tempfile
import unittest

# Import the module under test
import VersionStamper


class TestVersionStamper(unittest.TestCase):
    """Tests for the VersionStamper module."""

    def setUp(self):
        """Creates a temporary directory and a dummy JSON file."""
        self.test_dir = tempfile.mkdtemp()
        self.test_file_path = os.path.join(self.test_dir, 'AppVersion.json')

        # Create a mock existing file with some static data
        self.initial_data = {
            'Game': {
                'Name': 'TestGame',
                'Major': 1,
                'Minor': 2,
                'Patch': 3
            }
        }
        with open(self.test_file_path, 'w', encoding='utf-8') as f:
            json.dump(self.initial_data, f)

    def tearDown(self):
        """Cleans up the temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_update_preserves_static_data(self):
        """Verifies that Major/Minor versions are not overwritten."""
        VersionStamper.update_version_file(self.test_file_path)

        with open(self.test_file_path, 'r', encoding='utf-8') as f:
            new_data = json.load(f)

        self.assertEqual(new_data['Game']['Major'], 1)
        self.assertEqual(new_data['Game']['Minor'], 2)

    def test_update_injects_build_metadata(self):
        """Verifies that Hash and Date are injected correctly."""
        VersionStamper.update_version_file(self.test_file_path)

        with open(self.test_file_path, 'r', encoding='utf-8') as f:
            new_data = json.load(f)

        self.assertIn('Build', new_data)
        self.assertIn('Hash', new_data['Build'])
        self.assertIn('Date', new_data['Build'])
        self.assertTrue(len(new_data['Build']['Hash']) > 0)

    def test_handles_missing_file(self):
        """Verifies it creates the file if it doesn't exist."""
        os.remove(self.test_file_path)  # Delete the setup file

        VersionStamper.update_version_file(self.test_file_path)

        self.assertTrue(os.path.exists(self.test_file_path))
        with open(self.test_file_path, 'r', encoding='utf-8') as f:
            new_data = json.load(f)
        self.assertIn('Build', new_data)


if __name__ == '__main__':
    unittest.main()
