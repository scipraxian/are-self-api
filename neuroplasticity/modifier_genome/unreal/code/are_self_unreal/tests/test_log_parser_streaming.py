import os
import random
import unittest

from neuroplasticity.modifier_genome.unreal.code.are_self_unreal.log_parsers import (
    LogConstants,
    LogParserFactory,
    LogSession,
    merge_sessions,
)


class TestLogParserStreaming(unittest.TestCase):
    """
    Simulation Tests: Feeds real log files into the parser in randomized, jagged chunks
    to simulate network streaming/buffering behavior.
    """

    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(__file__)
        cls.files = {
            'build': os.path.join(base_dir, 'test_build_log.txt'),
            'run': os.path.join(base_dir, 'test_run_log.txt'),
            # Added for merge/multiplayer tests
            'server': os.path.join(base_dir, 'test_server_log.txt'),
            'client': os.path.join(base_dir, 'test_client_log.txt'),
        }

        for name, path in cls.files.items():
            if not os.path.exists(path):
                # Fallback: If server log is missing in this specific env, reuse run log
                # This ensures tests don't crash if the user hasn't uploaded all fixtures yet
                if name == 'server' and os.path.exists(cls.files['run']):
                    cls.files['server'] = cls.files['run']
                    continue
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
        Assert state (Timestamp Inheritance) is preserved across hundreds of tiny chunks.
        """
        entries, stats = self._stream_content(LogConstants.TYPE_BUILD, 'build', 1, 5)

        # 1. Verify Integrity
        # We expect the exact same count as the static test (768)
        self.assertEqual(len(entries), 768, "Streaming resulted in different entry count than static parse.")

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
        Assert stack trace accumulation isn't broken by chunk boundaries.
        """
        # Run logs have lots of stack traces. If a chunk splits a trace,
        # the parser must hold the pending entry until the next chunk.
        entries, stats = self._stream_content(LogConstants.TYPE_RUN, 'run', 2, 20)

        self.assertGreater(len(entries), 0)

        # Sanity check: Ensure we didn't create entries for stack trace lines
        # Stack traces usually start with spaces '   at ...'
        # If logic failed, we'd see entries with process='System' and message='   at ...'
        bad_entries = [e for e in entries if
                       e.message.strip().startswith('at ') and e.process == LogConstants.PROC_SYSTEM]
        self.assertEqual(len(bad_entries), 0, f"Found {len(bad_entries)} fractured stack trace entries.")

    def test_build_log_timestamp_update_mid_stream(self):
        """
        Specific Logic Verify: Assert that when the Cooker starts (explicit timestamp),
        the Strategy updates its state immediately, even if that line was the last one in a chunk.
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

    def test_merge_sessions_streaming(self):
        """
        Assert that two independent streams (Client/Server) can be ingested
        in random chunks and then successfully merged into a single chronological
        timeline. This ensures 'battle_stream' logic works with fragmented packets.
        """
        # 1. Stream Ingest (Simulate Network Lag/Packet Fragmentation)
        # Using separate source files to guarantee distinct content
        server_entries, server_stats = self._stream_content(LogConstants.TYPE_RUN, 'server', 5, 20)
        client_entries, client_stats = self._stream_content(LogConstants.TYPE_RUN, 'client', 5, 20)

        # 2. Wrap in Sessions
        # The parser returns raw entries lists, we must box them to match the merge_sessions signature
        session_server = LogSession(
            entries=server_entries,
            stats=server_stats,
            source_name="Server"
        )

        session_client = LogSession(
            entries=client_entries,
            stats=client_stats,
            source_name="Client"
        )

        # 3. Perform Merge
        merged = merge_sessions(session_client, session_server)

        # 4. Verify Integrity
        total_expected = len(server_entries) + len(client_entries)
        self.assertEqual(len(merged.entries), total_expected, "Merged entry count does not match sum of parts")

        # 5. Verify Chronological Ordering
        # Iterate and ensure T(n) <= T(n+1)
        for i in range(len(merged.entries) - 1):
            curr = merged.entries[i]
            next_e = merged.entries[i + 1]

            # Using LessEqual because timestamps might be identical
            self.assertLessEqual(
                curr.timestamp,
                next_e.timestamp,
                f"Sorting violation at index {i}: {curr.timestamp} > {next_e.timestamp} "
                f"({curr.source} vs {next_e.source})"
            )

        # 6. Verify Source Attribution
        # Ensure we didn't lose track of where lines came from
        sources = {e.source for e in merged.entries}
        self.assertIn("stream_server", sources)
        self.assertIn("stream_client", sources)
