import unittest
from datetime import datetime

from neuroplasticity.modifier_genome.unreal.code.are_self_unreal.log_parsers import (
    LogConstants,
    LogEntry,
    LogParserFactory,
    LogPatterns,
    LogSession,
    UERunLogStrategy,
    merge_sessions,
)


class TestLogPatterns(unittest.TestCase):
    """Verify Regex patterns against various edge case strings."""

    def test_anchor_regex(self):
        line = "Log started at 1/8/2026 10:13:29 AM (2026...)"
        m = LogPatterns.ANCHOR.search(line)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "1/8/2026 10:13:29 AM")

    def test_standard_ue_regex_variants(self):
        # Case 1: Standard
        # Regex Groups: 1=FullTS, 2=Category, 3=Level(Optional), 4=Message
        line = "[2026.01.08-10.13.34:123]LogCook: Display: Hello"
        m = LogPatterns.STANDARD_UE.match(line)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "2026.01.08-10.13.34:123")  # Full TS
        self.assertEqual(m.group(2), "LogCook")  # Category

        # Case 2: With Thread ID
        line = "[2026.01.08-10.13.34:123][  0]LogCook: Display: Hello"
        m = LogPatterns.STANDARD_UE.match(line)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), "LogCook")  # Category is now Group 2

        # Case 3: Missing Level (Implicit Display)
        line = "[2026.01.08-10.13.34:123]LogConfig: CVar deferred"
        m = LogPatterns.STANDARD_UE.match(line)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), "LogConfig")
        self.assertIsNone(m.group(3))  # Level group is optional

    def test_gpu_profile_regex(self):
        line = "Log: PROFILEGPU: MainCam (1920x1080): total GPU time 12.5 ms"
        m = LogPatterns.GPU_PROFILE.search(line)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "MainCam")
        self.assertEqual(m.group(2), "12.5")


class TestLogStatsLogic(unittest.TestCase):
    """Verify Map/Reduce logic in _enrich_entry."""

    def setUp(self):
        self.strategy = UERunLogStrategy("test")
        self.dt = datetime.now()

    def _process(self, msg, level=LogConstants.LVL_DISPLAY):
        entry = LogEntry(self.dt, 1, "P", "C", level, msg, msg)
        self.strategy._enrich_entry(entry)
        return entry

    def test_counters(self):
        self._process("Something went wrong", LogConstants.LVL_ERROR)
        self._process("Watch out", LogConstants.LVL_WARNING)
        self._process("Just info")

        self.assertEqual(self.strategy.stats.error_count, 1)
        self.assertEqual(self.strategy.stats.warning_count, 1)

    def test_gpu_rolling_average(self):
        self._process("PROFILEGPU: Cam1: total GPU time 10.0 ms")
        self.assertEqual(self.strategy.stats.avg_gpu_ms, 10.0)

        self._process("PROFILEGPU: Cam1: total GPU time 20.0 ms")
        self.assertEqual(self.strategy.stats.avg_gpu_ms, 15.0)

    def test_cook_stats(self):
        msg = "LogCook: Display: Cook Diagnostics: OpenFileHandles=100, VirtualMemory=2048MiB"
        entry = self._process(msg)

        self.assertEqual(self.strategy.stats.cook_open_handles, 100)
        self.assertEqual(self.strategy.stats.cook_virtual_mem_mb, 2048)
        self.assertTrue(entry.metadata.get(LogConstants.KEY_COOK_STATS))

    def test_build_outcomes(self):
        self._process("BUILD SUCCESSFUL")
        self.assertEqual(self.strategy.stats.build_outcome, LogConstants.OUTCOME_SUCCESS)

        self._process("BUILD FAILED")
        self.assertEqual(self.strategy.stats.build_outcome, LogConstants.OUTCOME_FAILURE)


class TestStrategies(unittest.TestCase):
    """Verify Strategy State Machines."""

    def test_factory_validation(self):
        with self.assertRaises(ValueError):
            LogParserFactory.create("invalid_type", "src")

    def test_build_strategy_anchor_logic(self):
        strat = LogParserFactory.create(LogConstants.TYPE_BUILD, "build")

        lines = ["Log started at 1/1/2026 10:00:00 AM"]
        entries = strat.parse_chunk(lines)
        entries += strat.flush()

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].timestamp.year, 2026)
        anchor_time = entries[0].timestamp

        entries = strat.parse_chunk(["LogCook: Display: Working..."])
        entries += strat.flush()
        self.assertEqual(entries[0].timestamp, anchor_time)

    def test_run_strategy_agent_time_resolution(self):
        strat = LogParserFactory.create(LogConstants.TYPE_RUN, "run")
        base_date = strat.current_timestamp.date()

        lines = ["14:30:00 [INFO] Agent started"]
        entries = strat.parse_chunk(lines) + strat.flush()

        self.assertEqual(entries[0].timestamp.hour, 14)
        self.assertEqual(entries[0].timestamp.minute, 30)
        self.assertEqual(entries[0].timestamp.date(), base_date)

    def test_stack_trace_accumulation(self):
        """Assert orphan lines attach to previous entry."""
        strat = LogParserFactory.create(LogConstants.TYPE_RUN, "run")

        lines = [
            "[2026.01.01-10.00.00:000]LogTemp: Error: Crash!",
            "  at Module.FunctionA",
            "  at Module.FunctionB"
        ]

        entries = strat.parse_chunk(lines) + strat.flush()

        self.assertEqual(len(entries), 1)
        self.assertIn("FunctionA", entries[0].message)
        self.assertIn("FunctionB", entries[0].message)


class TestMerger(unittest.TestCase):

    def test_merge_sessions(self):
        t1 = datetime(2026, 1, 1, 10, 0, 0)
        t2 = datetime(2026, 1, 1, 10, 0, 5)
        t3 = datetime(2026, 1, 1, 10, 0, 10)

        s1 = LogSession(entries=[LogEntry(t1, 1, "A", "C", "L", "M1", "R")], source_name="s1")
        s2 = LogSession(entries=[LogEntry(t2, 1, "B", "C", "L", "M2", "R")], source_name="s2")

        s1.entries.append(LogEntry(t3, 2, "A", "C", "L", "M3", "R"))

        merged = merge_sessions(s1, s2)

        self.assertEqual(len(merged.entries), 3)
        self.assertEqual(merged.entries[0].message, "M1")
        self.assertEqual(merged.entries[1].message, "M2")
        self.assertEqual(merged.entries[2].message, "M3")
        self.assertEqual(merged.stats.duration_seconds, 10.0)
