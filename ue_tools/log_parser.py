import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


class LogConstants(object):
    """Constants for dictionary keys and semantic labels."""
    # Strategy Types
    TYPE_BUILD = 'build'
    TYPE_RUN = 'run'

    # Metadata Keys
    KEY_CAMERA = 'camera'
    KEY_GPU_MS = 'gpu_ms'
    KEY_OPEN_HANDLES = 'open_file_handles'
    KEY_VIRTUAL_MEM = 'virtual_memory_mb'
    KEY_OUTCOME = 'outcome'
    KEY_BUILD_OUTCOME = 'build_outcome'
    KEY_COOK_STATS = 'has_cook_stats'

    # Sources
    SOURCE_UNKNOWN = 'unknown'

    # Outcomes
    OUTCOME_SUCCESS = 'SUCCESS'
    OUTCOME_FAILURE = 'FAILURE'

    # Date Formats
    FMT_ANCHOR = '%m/%d/%Y %I:%M:%S %p'
    FMT_UE_TIMESTAMP = '%Y.%m.%d-%H.%M.%S:%f'
    FMT_AGENT_TIME = '%H:%M:%S'

    # Process Names
    PROC_SYSTEM = 'System'
    PROC_EDITOR = 'Editor'
    PROC_AGENT = 'Agent'
    PROC_UAT = 'UAT'

    # Categories
    CAT_LOG_START = 'LogStart'
    CAT_AGENT_LOG = 'AgentLog'
    CAT_INFO = 'Info'
    CAT_BUILD_STATUS = 'BuildStatus'

    # Levels
    LVL_DISPLAY = 'Display'
    LVL_ERROR = 'Error'
    LVL_WARNING = 'Warning'


class LogPatterns(object):
    """Central repository for Log Regex Patterns."""
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


@dataclass
class LogStats:
    """Accumulator for session statistics."""
    error_count: int = 0
    warning_count: int = 0
    duration_seconds: float = 0.0
    gpu_frames_captured: int = 0
    avg_gpu_ms: float = 0.0
    cook_virtual_mem_mb: int = 0
    cook_open_handles: int = 0
    build_outcome: Optional[str] = None


@dataclass
class LogEntry:
    """The atomic unit of a log."""
    timestamp: datetime
    line_num: int
    process: str
    category: str
    level: str
    message: str
    raw: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = LogConstants.SOURCE_UNKNOWN


@dataclass
class LogSession:
    """Container for a parsed log session."""
    entries: List[LogEntry] = field(default_factory=list)
    stats: LogStats = field(default_factory=LogStats)
    source_name: str = LogConstants.SOURCE_UNKNOWN


class LogParserStrategy(ABC):
    """Abstract Base Class for stateful log parsing strategies."""

    def __init__(self, source_name: str = LogConstants.SOURCE_UNKNOWN):
        self.source_name = source_name
        self.current_timestamp: datetime = datetime.now()
        self.stats = LogStats()
        self._pending_entry: Optional[LogEntry] = None
        self._line_counter = 0

    @abstractmethod
    def parse_chunk(self, lines: List[str]) -> List[LogEntry]:
        """Process a list of lines and return completed entries."""
        pass

    def flush(self) -> List[LogEntry]:
        """Return any remaining pending entry."""
        if self._pending_entry:
            e = self._pending_entry
            # CRITICAL FIX: Must enrich the final entry before returning it
            self._enrich_entry(e)
            self._pending_entry = None
            return [e]
        return []

    def _finalize_pending(self) -> Optional[LogEntry]:
        """Completes the current entry and updates stats."""
        if self._pending_entry:
            entry = self._pending_entry
            self._enrich_entry(entry)
            self._pending_entry = None
            return entry
        return None

    def _create_pending(self, dt: datetime, process: str, category: str,
                        level: str, message: str, raw: str):
        """Starts a new pending entry."""
        safe_level = level if level else LogConstants.LVL_DISPLAY
        self._pending_entry = LogEntry(timestamp=dt,
                                       line_num=self._line_counter,
                                       process=process,
                                       category=category,
                                       level=safe_level,
                                       message=message,
                                       raw=raw,
                                       source=self.source_name)

    def _enrich_entry(self, entry: LogEntry) -> None:
        """Map/Reduce logic. Updates stats in-place."""
        # 1. Counters
        if LogConstants.LVL_ERROR in entry.level or LogConstants.LVL_ERROR in entry.message:
            self.stats.error_count += 1
        if LogConstants.LVL_WARNING in entry.level or LogConstants.LVL_WARNING in entry.message:
            self.stats.warning_count += 1

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

    def _resolve_agent_time(self, time_str: str) -> datetime:
        try:
            t = datetime.strptime(time_str, LogConstants.FMT_AGENT_TIME).time()
            return datetime.combine(self.current_timestamp.date(), t)
        except ValueError:
            return self.current_timestamp


class UEBuildLogStrategy(LogParserStrategy):
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


class UERunLogStrategy(LogParserStrategy):
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


class LogParserFactory(object):
    """Factory to create the correct strategy."""

    @staticmethod
    def create(log_type: str, source_label: str) -> LogParserStrategy:
        if log_type == LogConstants.TYPE_BUILD:
            return UEBuildLogStrategy(source_name=source_label)
        elif log_type == LogConstants.TYPE_RUN:
            return UERunLogStrategy(source_name=source_label)
        else:
            raise ValueError(f'Unknown log type: {log_type}')


def merge_sessions(session_a: LogSession, session_b: LogSession) -> LogSession:
    """Combines two log sessions into a single chronological stream."""
    merged = LogSession()
    merged.source_name = f'{session_a.source_name}+{session_b.source_name}'

    merged.entries = session_a.entries + session_b.entries
    merged.entries.sort(key=lambda x: x.timestamp)

    merged.stats.error_count = (
        session_a.stats.error_count + session_b.stats.error_count)
    merged.stats.warning_count = (
        session_a.stats.warning_count + session_b.stats.warning_count)

    if merged.entries:
        start = merged.entries[0].timestamp
        end = merged.entries[-1].timestamp
        merged.stats.duration_seconds = (end - start).total_seconds()

    return merged
