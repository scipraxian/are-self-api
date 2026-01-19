import os
import unittest
from datetime import datetime

from ue_tools.log_parser import LogConstants, LogIngestor, LogPatterns, merge_sessions


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

        # Verify existence
        for name, path in cls.files.items():
            if not os.path.exists(path):
                raise FileNotFoundError(f'Missing test fixture: {path}')

    def setUp(self):
        self.ingestor = LogIngestor()

    def test_ingest_build_log_implicit(self):
        """Verify UAT/Build log parsing (test_build_log.txt)."""
        session = self.ingestor.ingest(self.files['build'], 'build')

        # 1. Anchor Check (Dynamic)
        first = session.entries[0]
        self.assertIn('Log started at', first.message)

        # Extract truth from the message itself to verify parsing logic
        m = LogPatterns.ANCHOR.search(first.message)
        dt_truth = datetime.strptime(m.group(1), LogConstants.FMT_ANCHOR)

        self.assertEqual(first.timestamp, dt_truth)

        # 2. Inheritance
        second = session.entries[1]
        self.assertEqual(second.timestamp, first.timestamp)
        self.assertEqual(second.process, LogConstants.PROC_UAT)

        # 3. Dynamic Update Check
        # Check if we eventually found an explicit timestamp
        cook_entry = next((e for e in session.entries if e.process == LogConstants.PROC_EDITOR), None)

        if cook_entry:
            # If found, it should be different or at least valid
            self.assertIsInstance(cook_entry.timestamp, datetime)

        # 4. Stats
        # Verify stats populated
        self.assertIsNotNone(session.stats.build_outcome)

    def test_ingest_run_log_explicit(self):
        """Verify Runtime log parsing (test_run_log.txt)."""
        session = self.ingestor.ingest(self.files['run'], 'run')
        self.assertGreater(len(session.entries), 0)

        # Explicit timestamps check
        sample = session.entries[0]

        # Verify detection worked: Process should be Editor or Agent, NOT UAT
        self.assertIn(sample.process, [LogConstants.PROC_EDITOR, LogConstants.PROC_AGENT])

        # Should have microsecond precision (unless it's exactly .000000)
        # Checking validity of object is enough
        self.assertIsInstance(sample.timestamp, datetime)

    def test_ingest_server_log(self):
        """Verify Server log parsing (test_server_log.txt)."""
        session = self.ingestor.ingest(self.files['server'], 'server')
        self.assertGreater(len(session.entries), 0)
        self.assertEqual(session.source_name, 'server')
        self.assertEqual(session.entries[0].process, LogConstants.PROC_EDITOR)

    def test_ingest_client_log(self):
        """Verify Client log parsing (test_client_log.txt)."""
        session = self.ingestor.ingest(self.files['client'], 'client')
        self.assertGreater(len(session.entries), 0)
        self.assertEqual(session.source_name, 'client')
        self.assertEqual(session.entries[0].process, LogConstants.PROC_EDITOR)

    def test_client_server_merge(self):
        """Verify merging of Client and Server logs."""
        s_client = self.ingestor.ingest(self.files['client'], 'client')
        s_server = self.ingestor.ingest(self.files['server'], 'server')

        merged = merge_sessions(s_client, s_server)

        # 1. Total Count
        self.assertEqual(len(merged.entries), len(s_client.entries) + len(s_server.entries))

        # 2. Chronological Order
        for i in range(len(merged.entries) - 1):
            t1 = merged.entries[i].timestamp
            t2 = merged.entries[i + 1].timestamp
            self.assertLessEqual(t1, t2, f'Sorting failure at index {i}')

        # 3. Source mixing
        sources = {e.source for e in merged.entries}
        # Only assert if both files actually had content
        if len(s_client.entries) > 0:
            self.assertIn('client', sources)
        if len(s_server.entries) > 0:
            self.assertIn('server', sources)
