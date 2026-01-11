from django.test import SimpleTestCase
from talos_occipital.readers import read_build_log, strip_timestamps
from unittest.mock import patch, MagicMock


class ReadersTest(SimpleTestCase):

    def test_strip_timestamps(self):
        line = "[2026-01-11 10:00:00] Hello World"
        cleaned = strip_timestamps(line)
        self.assertEqual(cleaned.strip(), "Hello World")

    @patch('talos_occipital.readers.HydraSpawn')
    def test_read_build_log_regex(self, mock_spawn_cls):
        # Setup Mock Spawn and Head
        mock_spawn = MagicMock()
        mock_head = MagicMock()
        mock_head.id = 1
        mock_head.spell.name = "TestSpell"

        # Mock QuerySet behavior
        mock_qs = MagicMock()
        mock_qs.exists.return_value = True
        mock_qs.__iter__.return_value = iter([mock_head])

        mock_spawn.heads.filter.return_value = mock_qs
        mock_spawn.heads.all.return_value = mock_qs
        mock_spawn_cls.objects.get.return_value = mock_spawn

        # Log with real errors and false positives
        mock_head.spell_log = """
[2026-01-11 10:00:01] LogTemp: Display: Building...
[2026-01-11 10:00:02] LogTemp: Error: Critical Failure in Module X
[2026-01-11 10:00:03] LogTemp: Display: Still Trying...
[2026-01-11 10:00:04] Cmd: Success - 0 Error(s), 0 Warning(s)
[2026-01-11 10:00:05] LogTemp: Display: Done.
"""
        # Run
        summary = read_build_log(1)

        # Assertions
        self.assertIn("LogTemp: Error: Critical Failure in Module X", summary)
        self.assertIn("still trying...", summary.lower())
        # Ensure context is captured

        # Should NOT capture "Success - 0 Error(s)" as an error block
        # We can check if it appears in LAST 200 LINES (it will)
        # But we want to ensure it didn't trigger a "Concern Pattern" block if it was the ONLY thing.
        # In our mock logic, if it triggered, it would be in ERROR SUMMARY.
        # But wait, "Success - 0 Error(s)" is in IGNORE_PATTERNS, so it should NOT be in ERROR SUMMARY.
        # However, "Critical Failure" IS in ERROR SUMMARY.

        # Let's verify false positive logic specifically
        mock_head.spell_log = """
[2026-01-11 10:00:04] Cmd: Success - 0 Error(s), 0 Warning(s)
"""
        summary_clean = read_build_log(1)
        # ERROR SUMMARY should be empty (just newlines or empty string)
        self.assertNotIn("ERROR SUMMARY:\n...", summary_clean)
        self.assertNotIn("Cmd: Success",
                         summary_clean.split("LAST 200 LINES")[0])
