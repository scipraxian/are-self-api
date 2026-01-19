import os
import unittest

from ue_tools.log_parser import LogIngestor


class TestLogParserWithRealFile(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """
        Locate and read the REAL log file once.
        """
        # File is expected to be in the same directory as this test script
        cls.log_path = os.path.join(os.path.dirname(__file__), 'test_build_log.txt')

        if not os.path.exists(cls.log_path):
            raise FileNotFoundError(f"CRITICAL: Could not find test fixture at {cls.log_path}")

        with open(cls.log_path, 'r', encoding='utf-8') as f:
            cls.raw_lines = f.readlines()

    def setUp(self):
        self.parser = LogIngestor()
        # Parse the real file content
        self.entries = self.parser.parse(self.raw_lines)

    def test_file_ingestion_volume(self):
        """Verify we parsed a significant number of lines from the real file."""
        # The file is large; we expect thousands of entries, but at least > 100 for a sanity check
        self.assertGreater(len(self.entries), 100, "Parser returned too few entries for a full build log.")

    def test_anchor_chronometry(self):
        """
        Verify the timestamp from the first line:
        'Log started at 1/8/2026 10:13:29 AM'
        """
        first_entry = self.entries[0]

        # 1. Content Check
        self.assertIn("Log started at", first_entry.message)

        # 2. Timestamp Precision Check
        ts = first_entry.timestamp
        self.assertEqual(ts.year, 2026)
        self.assertEqual(ts.month, 1)
        self.assertEqual(ts.day, 8)
        self.assertEqual(ts.hour, 10)
        self.assertEqual(ts.minute, 13)
        self.assertEqual(ts.second, 29)

    def test_uat_timestamp_inheritance(self):
        """
        Verify a UAT line (no timestamp) inherits the anchor time.
        Target Line: 'Starting AutomationTool...'
        """
        # Find the specific entry
        target_entry = next((e for e in self.entries if "Starting AutomationTool" in e.message), None)
        self.assertIsNotNone(target_entry, "Could not find 'Starting AutomationTool' line.")

        # It should share the exact timestamp of the anchor (since it has none of its own)
        # 1/8/2026 10:13:29 AM
        ts = target_entry.timestamp
        self.assertEqual(ts.minute, 13)
        self.assertEqual(ts.second, 29)
        self.assertEqual(target_entry.process, "UAT")

    def test_ue_timestamp_parsing(self):
        """
        Verify a standard UE log line with explicit timestamp.
        Target: [2026.01.08-10.13.34:123]LogCook: Display: Cooked packages...
        """
        # Search for the entry by its unique timestamp signature in the raw text
        target_entry = next((e for e in self.entries if "10.13.34:123" in e.raw), None)
        self.assertIsNotNone(target_entry, "Could not find specific timestamped UE line.")

        # Verify parsed time matches the bracketed time, NOT the anchor time
        # 10:13:34 != 10:13:29
        self.assertEqual(target_entry.timestamp.minute, 13)
        self.assertEqual(target_entry.timestamp.second, 34)
        self.assertEqual(target_entry.timestamp.microsecond, 123000)

        self.assertEqual(target_entry.process, "Editor")
        self.assertEqual(target_entry.category, "LogCook")

    def test_forensic_metadata_cook(self):
        """
        Verify Cook Diagnostics metadata extraction.
        Target: LogCook: Display: Cook Diagnostics: OpenFileHandles=5359, VirtualMemory=5419MiB...
        """
        target_entry = next(
            (e for e in self.entries if "Cook Diagnostics" in e.message and "OpenFileHandles" in e.message), None)
        self.assertIsNotNone(target_entry, "Could not find Cook Diagnostics line.")

        # Check extracted metadata
        self.assertIn("open_file_handles", target_entry.metadata)
        self.assertIn("virtual_memory_mb", target_entry.metadata)

        # Verify exact values from file
        self.assertEqual(target_entry.metadata['open_file_handles'], 5359)
        self.assertEqual(target_entry.metadata['virtual_memory_mb'], 5419)

    def test_build_outcome_success(self):
        """
        Verify the parser caught the final 'BUILD SUCCESSFUL' line.
        """
        # Usually the last entry, but let's search to be safe in case of trailing newlines
        success_entry = next((e for e in self.entries if "BUILD SUCCESSFUL" in e.message), None)
        self.assertIsNotNone(success_entry, "Parser failed to capture BUILD SUCCESSFUL.")

        self.assertEqual(success_entry.metadata.get('build_outcome'), "SUCCESS")

    def test_warning_summary_capture(self):
        """
        Verify the LogInit summary block is parsed.
        Target: LogInit: Display: Success - 0 error(s), 4 warning(s)
        """
        summary_entry = next((e for e in self.entries if "Success - 0 error(s), 4 warning(s)" in e.message), None)
        self.assertIsNotNone(summary_entry, "Could not find Build Summary line.")
        self.assertEqual(summary_entry.category, "LogInit")


if __name__ == '__main__':
    unittest.main()