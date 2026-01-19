import unittest

from ue_tools.log_parser import LogIngestor


class TestLogParser(unittest.TestCase):

    def setUp(self):
        self.parser = LogIngestor()

    def test_parse_uat_header(self):
        """
        Feed the parser the first 5 lines of the UAT log.
        Assert: The Log started at... line is parsed, and subsequent lines (like Starting AutomationTool...) 
        inherit that datetime (by being appended or essentially treated within that context).
        """
        lines = [
            "Log started at 1/8/2026 10:13:29 AM (2026-01-08T18:13:29Z)",
            "Starting AutomationTool...",
            "Parsing command line: BuildCookRun -project=\"C:\\HSHVacancy.uproject\" -platform=Win64 -clientconfig=Development",
            "Running on Windows as a 64-bit process.",
            "CWD=C:\\Program Files\\Epic Games\\UE_5.6"
        ]
        entries = self.parser.parse(lines)

        # The first line is an anchor.
        # The subsequent lines do not match "Cat: Lev: Msg" so they are appended to the first entry.
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].process, "UAT")
        self.assertIn("Starting AutomationTool...", entries[0].message)
        self.assertIn("Parsing command line:", entries[0].message)

        # Check Timestamp Parsing
        # 1/8/2026 10:13:29 AM
        ts = entries[0].timestamp
        self.assertEqual(ts.year, 2026)
        self.assertEqual(ts.month, 1)
        self.assertEqual(ts.day, 8)
        self.assertEqual(ts.hour, 10)
        self.assertEqual(ts.minute, 13)
        self.assertEqual(ts.second, 29)

    def test_parse_cook_diagnostics(self):
        """
        Input: LogCook: Display: Cook Diagnostics: OpenFileHandles=251, VirtualMemory=2182MiB
        Assert: entry.metadata['open_file_handles'] == 251 and entry.metadata['virtual_memory_mb'] == 2182.
        """
        # We add a preceding line to establish a timestamp, otherwise it defaults to now()
        lines = [
            "[2026.01.08-10.13.34:123]LogCook: Display: Cooked packages 0 Packages Remain 424 Total 424",
            "LogCook: Display: Cook Diagnostics: OpenFileHandles=251, VirtualMemory=2182MiB"
        ]
        entries = self.parser.parse(lines)

        self.assertEqual(len(entries), 2)
        diag_entry = entries[1]

        self.assertEqual(diag_entry.category, "LogCook")
        self.assertEqual(diag_entry.metadata.get('open_file_handles'), 251)
        self.assertEqual(diag_entry.metadata.get('virtual_memory_mb'), 2182)
        # Verify timestamp inheritance
        self.assertEqual(diag_entry.timestamp, entries[0].timestamp)

    def test_parse_stack_trace_preservation(self):
        """
        Input:
        LogBlueprint: Error: Bad things happened
          at Script.CallFunction...
          at Script.AnotherThing...
        Assert: This produces one LogEntry. The message should contain the error plus the two stack trace lines.
        """
        lines = [
            "LogBlueprint: Error: Bad things happened",
            "  at Script.CallFunction...", "  at Script.AnotherThing..."
        ]
        entries = self.parser.parse(lines)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].category, "LogBlueprint")
        self.assertEqual(entries[0].level, "Error")
        self.assertIn("Bad things happened", entries[0].message)
        self.assertIn("at Script.CallFunction...", entries[0].message)
        self.assertIn("at Script.AnotherThing...", entries[0].message)

    def test_gpu_analytics(self):
        """
        Input: Log: PROFILEGPU: MainMenuPerfCam (1280x720): total GPU time 12.54 ms
        Assert: entry.metadata['gpu_ms'] == 12.54.
        """
        lines = [
            "Log: PROFILEGPU: MainMenuPerfCam (1280x720): total GPU time 12.54 ms"
        ]
        entries = self.parser.parse(lines)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].metadata.get('gpu_ms'), 12.54)
        self.assertEqual(entries[0].metadata.get('camera'), "MainMenuPerfCam")

    def test_build_outcome(self):
        lines = ["BUILD SUCCESSFUL"]
        entries = self.parser.parse(lines)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].metadata.get('build_outcome'), "SUCCESS")


if __name__ == '__main__':
    unittest.main()
