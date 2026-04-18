"""Unreal Engine log parser strategies.

Extends the generic core in `occipital_lobe.log_parser` with Unreal-flavored
regex patterns, constants, and streaming strategies for UE Build/UAT logs
and Runtime (Editor/Server/Client/Agent) logs. UE strategies register
themselves with the shared `LogParserFactory` at module import time.

Re-exports `LogEntry`, `LogSession`, `LogStats`, `LogParserFactory`, and
`merge_sessions` from the core so bundle-owned call sites (including the
`mcp_run_unreal_diagnostic_parser` tool) can import everything they need
from one place. The `LogConstants` exposed here is a UE-augmented subclass
of the core class — callers see both the generic fields and UE-specific
keys/formats/process labels on the same symbol.
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

    KEY_CAMERA = 'camera'
    KEY_GPU_MS = 'gpu_ms'
    KEY_OPEN_HANDLES = 'open_file_handles'
    KEY_VIRTUAL_MEM = 'virtual_memory_mb'
    KEY_OUTCOME = 'outcome'
    KEY_BUILD_OUTCOME = 'build_outcome'
    KEY_COOK_STATS = 'has_cook_stats'

    FMT_ANCHOR = '%m/%d/%Y %I:%M:%S %p'
    FMT_UE_TIMESTAMP = '%Y.%m.%d-%H.%M.%S:%f'

    PROC_SYSTEM = 'System'
    PROC_EDITOR = 'Editor'
    PROC_AGENT = 'Agent'
    PROC_UAT = 'UAT'

    CAT_LOG_START = 'LogStart'
    CAT_AGENT_LOG = 'AgentLog'
    CAT_BUILD_STATUS = 'BuildStatus'


class LogPatterns(object):
    """Central repository for UE log regex patterns."""

    ANCHOR = re.compile(
        r'Log started at (\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}:\d{2} [AP]M)'
    )

    STANDARD_UE = re.compile(
        r'^\[(\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{3})\]'
        r'(?:\[\s*\d+\])?\s*([^:]+):(?:\s*([^:]+):)?\s*(.*)'
    )

    AGENT_HEADER = re.compile(r'^(\d{2}:\d{2}:\d{2})\s+\[([^\]]+)\]\s+(.*)')

    UAT_HEADER = re.compile(r'^([a-zA-Z0-9_]+):\s*([a-zA-Z0-9_]+):\s*(.*)')

    BUILD_SUCCESS = re.compile(r'BUILD SUCCESSFUL')
    BUILD_FAILURE = re.compile(r'BUILD FAILED')

    GPU_PROFILE = re.compile(
        r'PROFILEGPU:\s*([\w]+).*total GPU time\s*([\d\.]+)\s*ms',
        re.IGNORECASE,
    )

    COOK_STATS = re.compile(r'OpenFileHandles=(\d+).*VirtualMemory=(\d+)MiB')


class UELogParserStrategy(LogParserStrategy):
    """UE-specific intermediate base.

    Adds GPU profiling / cook stats / build outcome enrichment on top of
    the generic error/warning counters provided by the core base.
    """

    def _enrich_entry(self, entry: LogEntry) -> None:
        super()._enrich_entry(entry)

        m_gpu = LogPatterns.GPU_PROFILE.search(entry.message)
        if m_gpu:
            cam = m_gpu.group(1)
            ms = float(m_gpu.group(2))
            entry.metadata[LogConstants.KEY_CAMERA] = cam
            entry.metadata[LogConstants.KEY_GPU_MS] = ms

            total_ms = (
                self.stats.avg_gpu_ms * self.stats.gpu_frames_captured
            ) + ms
            self.stats.gpu_frames_captured += 1
            self.stats.avg_gpu_ms = (
                total_ms / self.stats.gpu_frames_captured
            )

        m_cook = LogPatterns.COOK_STATS.search(entry.message)
        if m_cook:
            self.stats.cook_open_handles = int(m_cook.group(1))
            self.stats.cook_virtual_mem_mb = int(m_cook.group(2))
            entry.metadata[LogConstants.KEY_COOK_STATS] = True

        if LogPatterns.BUILD_SUCCESS.search(entry.message):
            self.stats.build_outcome = LogConstants.OUTCOME_SUCCESS
            entry.metadata[LogConstants.KEY_BUILD_OUTCOME] = (
                LogConstants.OUTCOME_SUCCESS
            )
        elif LogPatterns.BUILD_FAILURE.search(entry.message):
            self.stats.build_outcome = LogConstants.OUTCOME_FAILURE
            entry.metadata[LogConstants.KEY_BUILD_OUTCOME] = (
                LogConstants.OUTCOME_FAILURE
            )


class UEBuildLogStrategy(UELogParserStrategy):
    """Strategy for Build/UAT Logs (Implicit Mode)."""

    def parse_chunk(self, lines: List[str]) -> List[LogEntry]:
        completed = []

        for line in lines:
            self._line_counter += 1
            line = line.rstrip('\r\n')
            if not line:
                continue

            m_anchor = LogPatterns.ANCHOR.search(line)
            if m_anchor:
                if self._pending_entry:
                    completed.append(self._finalize_pending())

                try:
                    self.current_timestamp = datetime.strptime(
                        m_anchor.group(1), LogConstants.FMT_ANCHOR
                    )
                    self._create_pending(
                        self.current_timestamp,
                        LogConstants.PROC_SYSTEM,
                        LogConstants.CAT_LOG_START,
                        LogConstants.LVL_DISPLAY,
                        line,
                        line,
                    )
                    continue
                except ValueError:
                    pass

            m_std = LogPatterns.STANDARD_UE.match(line)
            if m_std:
                if self._pending_entry:
                    completed.append(self._finalize_pending())

                ts_str, cat, lvl, msg = m_std.groups()
                try:
                    self.current_timestamp = datetime.strptime(
                        ts_str, LogConstants.FMT_UE_TIMESTAMP
                    )
                    self._create_pending(
                        self.current_timestamp,
                        LogConstants.PROC_EDITOR,
                        cat.strip(),
                        lvl,
                        msg,
                        line,
                    )
                    continue
                except ValueError:
                    pass

            m_uat = LogPatterns.UAT_HEADER.match(line)
            if m_uat:
                if self._pending_entry:
                    completed.append(self._finalize_pending())

                cat, lvl, msg = m_uat.groups()

                proc = LogConstants.PROC_UAT
                if cat.startswith('Log') or cat == 'Cmd':
                    proc = LogConstants.PROC_EDITOR

                self._create_pending(
                    self.current_timestamp,
                    proc,
                    cat.strip(),
                    lvl,
                    msg,
                    line,
                )
                continue

            if self._pending_entry:
                self._pending_entry.message += '\n' + line
                self._pending_entry.raw += '\n' + line
            else:
                self._create_pending(
                    self.current_timestamp,
                    LogConstants.PROC_UAT,
                    LogConstants.CAT_INFO,
                    LogConstants.LVL_DISPLAY,
                    line,
                    line,
                )

        return completed


class UERunLogStrategy(UELogParserStrategy):
    """Strategy for Runtime/Server/Client Logs (Explicit Mode)."""

    def parse_chunk(self, lines: List[str]) -> List[LogEntry]:
        completed = []

        for line in lines:
            self._line_counter += 1
            line = line.rstrip('\r\n')
            if not line:
                continue

            m_std = LogPatterns.STANDARD_UE.match(line)
            if m_std:
                if self._pending_entry:
                    completed.append(self._finalize_pending())

                ts_str, cat, lvl, msg = m_std.groups()
                try:
                    self.current_timestamp = datetime.strptime(
                        ts_str, LogConstants.FMT_UE_TIMESTAMP
                    )
                    self._create_pending(
                        self.current_timestamp,
                        LogConstants.PROC_EDITOR,
                        cat.strip(),
                        lvl,
                        msg,
                        line,
                    )
                    continue
                except ValueError:
                    pass

            m_agent = LogPatterns.AGENT_HEADER.match(line)
            if m_agent:
                if self._pending_entry:
                    completed.append(self._finalize_pending())

                time_str, lvl, msg = m_agent.groups()
                dt = self._resolve_agent_time(time_str)
                self.current_timestamp = dt
                self._create_pending(
                    dt,
                    LogConstants.PROC_AGENT,
                    LogConstants.CAT_AGENT_LOG,
                    lvl.strip(),
                    msg,
                    line,
                )
                continue

            if self._pending_entry:
                self._pending_entry.message += '\n' + line
                self._pending_entry.raw += '\n' + line
            else:
                self._create_pending(
                    self.current_timestamp,
                    LogConstants.PROC_SYSTEM,
                    LogConstants.CAT_INFO,
                    LogConstants.LVL_DISPLAY,
                    line,
                    line,
                )

        return completed


# Register UE strategies with the shared factory at import time. Dict
# assignment is naturally idempotent — re-import (boot_bundles pops and
# re-imports on every AppConfig.ready) simply overwrites the existing
# registration with the same class reference.
LogParserFactory.register(LogConstants.TYPE_BUILD, UEBuildLogStrategy)
LogParserFactory.register(LogConstants.TYPE_RUN, UERunLogStrategy)
