"""Unreal Engine log parser strategies.

Extends the generic core in `occipital_lobe.log_parser` with Unreal-flavored
regex patterns, constants, and streaming strategies for UE Build/UAT logs
and Runtime (Editor/Server/Client/Agent) logs. UE strategies register
themselves with the shared `LogParserFactory` at module import time.

Re-exports `LogEntry`, `LogSession`, `LogStats`, `LogParserFactory`, and
`merge_sessions` from the core so existing `from ue_tools.log_parser import
...` call sites keep working. The `LogConstants` exposed here is a UE-
augmented subclass of the core class — tests and UE callers see both the
generic fields and UE-specific keys/formats/process labels on the same
symbol.
"""

import re
from datetime import datetime
from typing import List

from occipital_lobe.log_parser import LogConstants as _BaseLogConstants
from occipital_lobe.log_parser import (
    LogEntry,
    LogParserFactory,
    LogParserStrategy,
    LogSession,
    LogStats,
    merge_sessions,
)

__all__ = [
    'LogConstants',
    'LogEntry',
    'LogParserFactory',
    'LogParserStrategy',
    'LogPatterns',
    'LogSession',
    'LogStats',
    'UEBuildLogStrategy',
    'UELogParserStrategy',
    'UERunLogStrategy',
    'merge_sessions',
]


class LogConstants(_BaseLogConstants):
    """UE-extended constants — adds Unreal-specific keys, formats, labels."""

    # Metadata Keys (UE-specific)
    KEY_CAMERA = 'camera'
    KEY_GPU_MS = 'gpu_ms'
    KEY_OPEN_HANDLES = 'open_file_handles'
    KEY_VIRTUAL_MEM = 'virtual_memory_mb'
    KEY_OUTCOME = 'outcome'
    KEY_BUILD_OUTCOME = 'build_outcome'
    KEY_COOK_STATS = 'has_cook_stats'

    # Date Formats (UE-specific)
    FMT_ANCHOR = '%m/%d/%Y %I:%M:%S %p'
    FMT_UE_TIMESTAMP = '%Y.%m.%d-%H.%M.%S:%f'

    # Process Names (UE-specific)
    PROC_SYSTEM = 'System'
    PROC_EDITOR = 'Editor'
    PROC_AGENT = 'Agent'
    PROC_UAT = 'UAT'

    # Categories (UE-specific)
    CAT_LOG_START = 'LogStart'
    CAT_AGENT_LOG = 'AgentLog'
    CAT_BUILD_STATUS = 'BuildStatus'


class LogPatterns(object):
    """Central repository for UE log regex patterns."""
    # Anchor: "Log started at 1/8/2026 10:13:29 AM"
    ANCHOR = re.compile(
        r'Log started at (\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}:\d{2} [AP]M)')

    # Standard UE: "[2026.01.08-10.13.34:123][  0]LogCook: Display: ..."
    # Group 1: Full TS, Group 2: Category, Group 3: Level (Optional), Group 4: Message
    STANDARD_UE = re.compile(
        r'^\[(\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{3})\](?:\[\s*\d+\])?\s*([^:]+):(?:\s*([^:]+):)?\s*(.*)'
    )

    # Agent: "10:13:29 [INFO] ..."
    AGENT_HEADER = re.compile(r'^(\d{2}:\d{2}:\d{2})\s+\[([^\]]+)\]\s+(.*)')

    # UAT Header: "LogCook: Display: ..." (No Timestamp)
    UAT_HEADER = re.compile(r'^([a-zA-Z0-9_]+):\s*([a-zA-Z0-9_]+):\s*(.*)')

    # Build Outcome
    BUILD_SUCCESS = re.compile(r'BUILD SUCCESSFUL')
    BUILD_FAILURE = re.compile(r'BUILD FAILED')

    # Forensic / Metadata
    GPU_PROFILE = re.compile(
        r'PROFILEGPU:\s*([\w]+).*total GPU time\s*([\d\.]+)\s*ms',
        re.IGNORECASE)

    COOK_STATS = re.compile(r'OpenFileHandles=(\d+).*VirtualMemory=(\d+)MiB')


class UELogParserStrategy(LogParserStrategy):
    """UE-specific intermediate base.

    Adds GPU profiling / cook stats / build outcome enrichment on top of
    the generic error/warning counters provided by the core base.
    """

    def _enrich_entry(self, entry: LogEntry) -> None:
        # 1. Generic counters
        super()._enrich_entry(entry)

        # 2. GPU Profiling
        m_gpu = LogPatterns.GPU_PROFILE.search(entry.message)
        if m_gpu:
            cam = m_gpu.group(1)
            ms = float(m_gpu.group(2))
            entry.metadata[LogConstants.KEY_CAMERA] = cam
            entry.metadata[LogConstants.KEY_GPU_MS] = ms

            total_ms = (self.stats.avg_gpu_ms *
                        self.stats.gpu_frames_captured) + ms
            self.stats.gpu_frames_captured += 1
            self.stats.avg_gpu_ms = total_ms / self.stats.gpu_frames_captured

        # 3. Cook Stats
        m_cook = LogPatterns.COOK_STATS.search(entry.message)
        if m_cook:
            self.stats.cook_open_handles = int(m_cook.group(1))
            self.stats.cook_virtual_mem_mb = int(m_cook.group(2))
            entry.metadata[LogConstants.KEY_COOK_STATS] = True

        # 4. Build Outcome
        if LogPatterns.BUILD_SUCCESS.search(entry.message):
            self.stats.build_outcome = LogConstants.OUTCOME_SUCCESS
            entry.metadata[
                LogConstants.KEY_BUILD_OUTCOME] = LogConstants.OUTCOME_SUCCESS
        elif LogPatterns.BUILD_FAILURE.search(entry.message):
            self.stats.build_outcome = LogConstants.OUTCOME_FAILURE
            entry.metadata[
                LogConstants.KEY_BUILD_OUTCOME] = LogConstants.OUTCOME_FAILURE


class UEBuildLogStrategy(UELogParserStrategy):
    """
    Strategy for Build/UAT Logs (Implicit Mode).
    """

    def parse_chunk(self, lines: List[str]) -> List[LogEntry]:
        completed = []

        for line in lines:
            self._line_counter += 1
            line = line.rstrip('\r\n')
            if not line:
                continue

            # 1. Check for Anchor (High Priority Update)
            m_anchor = LogPatterns.ANCHOR.search(line)
            if m_anchor:
                if self._pending_entry:
                    completed.append(self._finalize_pending())

                try:
                    self.current_timestamp = datetime.strptime(
                        m_anchor.group(1), LogConstants.FMT_ANCHOR)
                    self._create_pending(self.current_timestamp,
                                         LogConstants.PROC_SYSTEM,
                                         LogConstants.CAT_LOG_START,
                                         LogConstants.LVL_DISPLAY, line, line)
                    continue
                except ValueError:
                    pass

            # 2. Check for Explicit Timestamp (Dynamic Update)
            m_std = LogPatterns.STANDARD_UE.match(line)
            if m_std:
                if self._pending_entry:
                    completed.append(self._finalize_pending())

                ts_str, cat, lvl, msg = m_std.groups()
                try:
                    self.current_timestamp = datetime.strptime(
                        ts_str, LogConstants.FMT_UE_TIMESTAMP)
                    self._create_pending(self.current_timestamp,
                                         LogConstants.PROC_EDITOR, cat.strip(),
                                         lvl, msg, line)
                    continue
                except ValueError:
                    pass

            # 3. Check for UAT Header (Inherit Time)
            m_uat = LogPatterns.UAT_HEADER.match(line)
            if m_uat:
                if self._pending_entry:
                    completed.append(self._finalize_pending())

                cat, lvl, msg = m_uat.groups()

                # Heuristic: Detect Editor lines masquerading as UAT
                proc = LogConstants.PROC_UAT
                if cat.startswith('Log') or cat == 'Cmd':
                    proc = LogConstants.PROC_EDITOR

                self._create_pending(self.current_timestamp, proc, cat.strip(),
                                     lvl, msg, line)
                continue

            # 4. Fallback (Append to Pending / Stack Trace)
            if self._pending_entry:
                self._pending_entry.message += '\n' + line
                self._pending_entry.raw += '\n' + line
            else:
                self._create_pending(self.current_timestamp,
                                     LogConstants.PROC_UAT,
                                     LogConstants.CAT_INFO,
                                     LogConstants.LVL_DISPLAY, line, line)

        return completed


class UERunLogStrategy(UELogParserStrategy):
    """
    Strategy for Runtime/Server/Client Logs (Explicit Mode).
    """

    def parse_chunk(self, lines: List[str]) -> List[LogEntry]:
        completed = []

        for line in lines:
            self._line_counter += 1
            line = line.rstrip('\r\n')
            if not line:
                continue

            # 1. Standard UE Check
            m_std = LogPatterns.STANDARD_UE.match(line)
            if m_std:
                if self._pending_entry:
                    completed.append(self._finalize_pending())

                ts_str, cat, lvl, msg = m_std.groups()
                try:
                    self.current_timestamp = datetime.strptime(
                        ts_str, LogConstants.FMT_UE_TIMESTAMP)
                    self._create_pending(self.current_timestamp,
                                         LogConstants.PROC_EDITOR, cat.strip(),
                                         lvl, msg, line)
                    continue
                except ValueError:
                    pass

            # 2. Agent Check
            m_agent = LogPatterns.AGENT_HEADER.match(line)
            if m_agent:
                if self._pending_entry:
                    completed.append(self._finalize_pending())

                time_str, lvl, msg = m_agent.groups()
                dt = self._resolve_agent_time(time_str)
                self.current_timestamp = dt
                self._create_pending(dt, LogConstants.PROC_AGENT,
                                     LogConstants.CAT_AGENT_LOG, lvl.strip(),
                                     msg, line)
                continue

            # 3. Fallback: Append to pending
            if self._pending_entry:
                self._pending_entry.message += '\n' + line
                self._pending_entry.raw += '\n' + line
            else:
                self._create_pending(self.current_timestamp,
                                     LogConstants.PROC_SYSTEM,
                                     LogConstants.CAT_INFO,
                                     LogConstants.LVL_DISPLAY, line, line)

        return completed


# Register UE strategies with the shared factory at import time.
LogParserFactory.register(LogConstants.TYPE_BUILD, UEBuildLogStrategy)
LogParserFactory.register(LogConstants.TYPE_RUN, UERunLogStrategy)
