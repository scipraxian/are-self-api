import os
import unittest

from ue_tools.log_parser import LogConstants, LogParserFactory, LogSession, merge_sessions


class TestLogParserWithRealFiles(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Locate all 4 real log files provided by user."""
        base_dir = os.path.dirname(__file__)
        cls.files = {
            'build': os.path.join(base_dir, 'test_build_log.txt'),
            'run': os.path.join(base_dir, 'test_run_log.txt'),
            'server': os.path.join(base_dir, 'test_server_log.txt'),
            'client': os.path.join(base_dir, 'test_client_log.txt'),
        }
        for name, path in cls.files.items():
            if not os.path.exists(path):
                raise FileNotFoundError(f'Missing test fixture: {path}')

    def read_file(self, key):
        with open(self.files[key], 'r', encoding='utf-8-sig', errors='replace') as f:
            return f.readlines()

    def test_build_strategy_streaming(self):
        """
        Verify Build Log Parsing with STREAMING (Chunked Input).
        Logic: Feed header in Chunk 1, Cook stats in Chunk 2.
        Assert: Timestamp from Chunk 1 is inherited by Chunk 2.
        Assert: EXACT count of 768 entries (Regression Lock).
        """
        lines = self.read_file('build')

        # Split into two arbitrary chunks
        midpoint = len(lines) // 2
        chunk1 = lines[:midpoint]
        chunk2 = lines[midpoint:]

        strategy = LogParserFactory.create(LogConstants.TYPE_BUILD, 'build_stream')

        # Ingest Chunk 1
        entries_1 = strategy.parse_chunk(chunk1)

        # Verify Anchor found in Chunk 1
        anchor = entries_1[0]
        self.assertIn('Log started at', anchor.message)
        anchor_ts = anchor.timestamp

        # Ingest Chunk 2
        entries_2 = strategy.parse_chunk(chunk2)

        # Verify Chunk 2 inherited the time
        implicit_entry = next((e for e in entries_2 if e.process == LogConstants.PROC_UAT), None)
        if implicit_entry:
            self.assertGreaterEqual(implicit_entry.timestamp, anchor_ts)

        entries_final = strategy.flush()

        total_entries = len(entries_1) + len(entries_2) + len(entries_final)

        # STRICT REGRESSION CHECK: Based on known static file parsing
        self.assertEqual(total_entries, 768, f"Expected exactly 768 entries, found {total_entries}")
        self.assertGreater(strategy.stats.warning_count, 0)

    def test_run_strategy_precision(self):
        """
        Verify Runtime Log Parsing (Explicit).
        """
        lines = self.read_file('run')
        strategy = LogParserFactory.create(LogConstants.TYPE_RUN, 'run_test')

        entries = strategy.parse_chunk(lines)
        entries += strategy.flush()

        self.assertGreater(len(entries), 0)

        # Verify Precision
        sample = next((e for e in entries if e.process == LogConstants.PROC_EDITOR), None)
        self.assertIsNotNone(sample)
        self.assertNotEqual(sample.timestamp.microsecond, 0)

    def test_client_server_merge(self):
        """
        Verify merging two EXPLICIT streams.
        """
        client_lines = self.read_file('client')
        server_lines = self.read_file('server')

        strat_c = LogParserFactory.create(LogConstants.TYPE_RUN, 'client')
        entries_c = strat_c.parse_chunk(client_lines) + strat_c.flush()
        session_c = LogSession(entries=entries_c, stats=strat_c.stats, source_name='client')

        strat_s = LogParserFactory.create(LogConstants.TYPE_RUN, 'server')
        entries_s = strat_s.parse_chunk(server_lines) + strat_s.flush()
        session_s = LogSession(entries=entries_s, stats=strat_s.stats, source_name='server')

        merged = merge_sessions(session_c, session_s)

        # Verify Sorting
        for i in range(len(merged.entries) - 1):
            t1 = merged.entries[i].timestamp
            t2 = merged.entries[i + 1].timestamp
            self.assertLessEqual(t1, t2, f'Sorting failure at index {i}')

        # Verify Source Mixing
        sources = {e.source for e in merged.entries}
        if len(entries_c) > 0: self.assertIn('client', sources)
        if len(entries_s) > 0: self.assertIn('server', sources)
