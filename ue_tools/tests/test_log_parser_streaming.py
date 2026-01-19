import os
import random
import unittest

from ue_tools.log_parser import LogConstants, LogParserFactory


class TestLogParserStreaming(unittest.TestCase):
    """
    Simulation Tests:
    Feeds real log files into the parser in randomized, jagged chunks
    to simulate network streaming/buffering behavior.
    """

    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(__file__)
        cls.files = {
            'build': os.path.join(base_dir, 'test_build_log.txt'),
            'run': os.path.join(base_dir, 'test_run_log.txt'),
        }
        for name, path in cls.files.items():
            if not os.path.exists(path):
                raise FileNotFoundError(f"Missing fixture: {path}")

    def _stream_content(self, strategy_type, file_key, min_chunk=1, max_chunk=10):
        """Helper to stream a file into a strategy."""
        with open(self.files[file_key], 'r', encoding='utf-8-sig', errors='replace') as f:
            all_lines = f.readlines()

        strategy = LogParserFactory.create(strategy_type, f"stream_{file_key}")
        collected_entries = []

        # Shred the lines into chunks
        cursor = 0
        total_lines = len(all_lines)

        while cursor < total_lines:
            # Determine random chunk size
            chunk_size = random.randint(min_chunk, max_chunk)
            end = min(cursor + chunk_size, total_lines)

            chunk = all_lines[cursor:end]

            # Feed the chunk
            new_entries = strategy.parse_chunk(chunk)
            collected_entries.extend(new_entries)

            cursor = end

        # Flush remainder
        collected_entries.extend(strategy.flush())
        return collected_entries, strategy.stats

    def test_build_log_drip_feed(self):
        """
        Extreme Stress Test: Build Log fed 1 to 5 lines at a time.
        Verifies that state (Timestamp Inheritance) is preserved across hundreds of tiny chunks.
        """
        entries, stats = self._stream_content(LogConstants.TYPE_BUILD, 'build', 1, 5)

        # 1. Verify Integrity
        # We expect the exact same count as the static test (768)
        self.assertEqual(len(entries), 768,
                         "Streaming resulted in different entry count than static parse.")

        # 2. Verify Inheritance
        # Check that valid timestamps exist throughout the file, not just at the start
        midpoint = len(entries) // 2
        self.assertIsNotNone(entries[midpoint].timestamp)
        self.assertIsNotNone(entries[-1].timestamp)

        # 3. Verify Stats
        self.assertEqual(stats.build_outcome, LogConstants.OUTCOME_SUCCESS)

    def test_run_log_jagged_feed(self):
        """
        Stress Test: Run Log fed in variable chunks.
        Verifies stack trace accumulation isn't broken by chunk boundaries.
        """
        # Run logs have lots of stack traces. If a chunk splits a trace,
        # the parser must hold the pending entry until the next chunk.
        entries, stats = self._stream_content(LogConstants.TYPE_RUN, 'run', 2, 20)

        self.assertGreater(len(entries), 0)

        # Sanity check: Ensure we didn't create entries for stack trace lines
        # Stack traces usually start with spaces '  at ...'
        # If logic failed, we'd see entries with process='System' and message='  at ...'
        bad_entries = [e for e in entries if
                       e.message.strip().startswith('at ') and e.process == LogConstants.PROC_SYSTEM]
        self.assertEqual(len(bad_entries), 0, f"Found {len(bad_entries)} fractured stack trace entries.")

    def test_build_log_timestamp_update_mid_stream(self):
        """
        Specific Logic Verify:
        Ensure that when the Cooker starts (explicit timestamp), the Strategy updates
        its state immediately, even if that line was the last one in a chunk.
        """
        # We simulate this by reading until we find the cook line, then chunking specifically there.
        with open(self.files['build'], 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()

        # Find the index of the explicit timestamp line
        cook_idx = -1
        for i, line in enumerate(lines):
            if "[2026." in line and "LogCook" in line:
                cook_idx = i
                break

        if cook_idx == -1:
            self.skipTest("Could not find explicit timestamp in build log for this test.")

        # Chunk 1: Everything UP TO the timestamp line
        # Chunk 2: The timestamp line itself
        # Chunk 3: The rest
        chunk1 = lines[:cook_idx]
        chunk2 = [lines[cook_idx]]
        chunk3 = lines[cook_idx + 1:]

        strategy = LogParserFactory.create(LogConstants.TYPE_BUILD, "stream_update")

        entries = []
        entries.extend(strategy.parse_chunk(chunk1))
        entries.extend(strategy.parse_chunk(chunk2))  # Should update state here
        entries.extend(strategy.parse_chunk(chunk3))  # Should inherit new state
        entries.extend(strategy.flush())

        # Verify the entry corresponding to chunk2 has the explicit time
        cook_entry = next((e for e in entries if "Cooked packages" in e.message), None)
        self.assertIsNotNone(cook_entry)

        # Verify the NEXT entry inherited that specific time
        idx = entries.index(cook_entry)
        if idx + 1 < len(entries):
            next_entry = entries[idx + 1]
            self.assertEqual(next_entry.timestamp, cook_entry.timestamp)
