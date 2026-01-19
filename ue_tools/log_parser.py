import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


class LogConstants(object):
    """Constants for dictionary keys and semantic labels."""
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

    # Strategies
    STRAT_EXPLICIT = 'EXPLICIT'
    STRAT_IMPLICIT = 'IMPLICIT'


class LogPatterns(object):
    """Central repository for Log Regex Patterns."""
    # Anchor: "Log started at 1/8/2026 10:13:29 AM"
    ANCHOR = re.compile(
        r'Log started at (\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}:\d{2} [AP]M)')

    # Timestamp Only: Used for detection [YYYY.MM.DD-HH.MM.SS:MS]
    TIMESTAMP_DETECTOR = re.compile(
        r'\[\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{3}\]')

    # Standard UE: "[2026.01.08-10.13.34:123][  0]LogCook: Display: ..."
    # Captures: 1=FullTS, 2=Category, 3=Level(Optional), 4=Message
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


def merge_sessions(session_a: LogSession, session_b: LogSession) -> LogSession:
    """Combines two log sessions into a single chronological stream."""
    merged = LogSession()
    merged.source_name = f'{session_a.source_name}+{session_b.source_name}'

    # Interleave entries
    merged.entries = session_a.entries + session_b.entries
    merged.entries.sort(key=lambda x: x.timestamp)

    # Merge Stats
    merged.stats.error_count = (
            session_a.stats.error_count + session_b.stats.error_count)
    merged.stats.warning_count = (
            session_a.stats.warning_count + session_b.stats.warning_count)

    # Duration is roughly the union
    start_a = session_a.entries[0].timestamp if session_a.entries else datetime.max
    start_b = session_b.entries[0].timestamp if session_b.entries else datetime.max
    end_a = session_a.entries[-1].timestamp if session_a.entries else datetime.min
    end_b = session_b.entries[-1].timestamp if session_b.entries else datetime.min

    effective_start = min(start_a, start_b)
    effective_end = max(end_a, end_b)

    if effective_start != datetime.max and effective_end != datetime.min:
        merged.stats.duration_seconds = (
                effective_end - effective_start).total_seconds()

    return merged


class LogIngestor(object):
    """
    Forensic Log Ingestion Engine.
    Detects format, parses lines, and aggregates statistics.
    """

    def ingest(self, file_path: str, source_label: str) -> LogSession:
        """
        Main Entry Point. Reads file and produces a LogSession.
        Using utf-8-sig to handle Byte Order Marks (BOM) automatically.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f'Log file not found: {file_path}')

        with open(file_path, 'r', encoding='utf-8-sig', errors='replace') as f:
            lines = f.readlines()

        session = LogSession(source_name=source_label)

        # 1. Strategy Detection (Scan more lines to be safe)
        strategy = self._detect_strategy(lines[:200])

        # 2. Parsing Loop
        current_anchor = datetime.now()  # Fallback

        for idx, line in enumerate(lines):
            line = line.rstrip('\r\n')
            if not line:
                continue

            line_num = idx + 1
            entry = None

            # Check for Anchor Updates (Universal priority)
            anchor_match = LogPatterns.ANCHOR.search(line)
            if anchor_match:
                try:
                    current_anchor = datetime.strptime(
                        anchor_match.group(1), LogConstants.FMT_ANCHOR)
                    # Create entry for the anchor itself
                    entry = LogEntry(current_anchor, line_num,
                                     LogConstants.PROC_SYSTEM,
                                     LogConstants.CAT_LOG_START,
                                     LogConstants.LVL_DISPLAY, line, line)
                except ValueError:
                    pass

            # Dispatch to Strategy
            if not entry:
                if strategy == LogConstants.STRAT_EXPLICIT:
                    entry, current_anchor = self._parse_explicit(
                        line, line_num, current_anchor)
                else:
                    entry, current_anchor = self._parse_implicit(
                        line, line_num, current_anchor)

            # 3. Aggregation (Map/Reduce)
            if entry:
                entry.source = source_label
                self._enrich_entry(entry, session.stats)
                session.entries.append(entry)
            else:
                # Stack Trace / Continuation Recovery
                if session.entries:
                    last = session.entries[-1]
                    last.message += '\n' + line
                    last.raw += '\n' + line

        # 4. Finalize Stats
        if session.entries:
            start = session.entries[0].timestamp
            end = session.entries[-1].timestamp
            session.stats.duration_seconds = (end - start).total_seconds()

        return session

    def _detect_strategy(self, snippet: List[str]) -> str:
        """
        Heuristic: If we see standard bracketed timestamps, it's EXPLICIT.
        Otherwise, it's IMPLICIT (Build/UAT) requiring anchor inheritance.
        """
        for line in snippet:
            # Using search instead of match handles indented timestamps or noise
            if LogPatterns.TIMESTAMP_DETECTOR.search(line):
                return LogConstants.STRAT_EXPLICIT
        return LogConstants.STRAT_IMPLICIT

    def _parse_explicit(self, line: str, line_num: int,
                        current_anchor: datetime) -> Tuple[Optional[LogEntry],
    datetime]:
        """
        Parses Runtime logs. Expects timestamps.
        Lines without timestamps are treated as None (stack traces).
        """
        # 1. Standard UE
        m_std = LogPatterns.STANDARD_UE.match(line)
        if m_std:
            # 4 Groups: TS, Cat, Level, Msg
            ts_str, cat, lvl, msg = m_std.groups()

            # Default level if missing
            if lvl is None:
                lvl = LogConstants.LVL_DISPLAY

            try:
                dt = datetime.strptime(ts_str, LogConstants.FMT_UE_TIMESTAMP)
                return LogEntry(dt, line_num, LogConstants.PROC_EDITOR,
                                cat.strip(), lvl.strip(), msg, line), dt
            except ValueError:
                pass

        # 2. Agent Format
        m_agent = LogPatterns.AGENT_HEADER.match(line)
        if m_agent:
            time_str, lvl, msg = m_agent.groups()
            dt = self._resolve_time(time_str, current_anchor)
            return LogEntry(dt, line_num, LogConstants.PROC_AGENT,
                            LogConstants.CAT_AGENT_LOG, lvl.strip(), msg,
                            line), dt

        # No timestamp match -> Return None to trigger stack trace accumulation
        return None, current_anchor

    def _parse_implicit(self, line: str, line_num: int,
                        current_anchor: datetime) -> Tuple[Optional[LogEntry],
    datetime]:
        """
        Parses Build/UAT logs. Aggressively inherits timestamps.
        """
        # 1. Check for Explicit timestamp inside Build log
        m_std = LogPatterns.STANDARD_UE.match(line)
        if m_std:
            ts_str, cat, lvl, msg = m_std.groups()

            if lvl is None:
                lvl = LogConstants.LVL_DISPLAY

            try:
                dt = datetime.strptime(ts_str, LogConstants.FMT_UE_TIMESTAMP)
                return LogEntry(dt, line_num, LogConstants.PROC_EDITOR,
                                cat.strip(), lvl.strip(), msg, line), dt
            except ValueError:
                pass

        # 2. Check for UAT Header
        m_uat = LogPatterns.UAT_HEADER.match(line)
        if m_uat:
            cat, lvl, msg = m_uat.groups()
            # Inherit current_anchor
            return LogEntry(current_anchor, line_num, LogConstants.PROC_UAT,
                            cat.strip(), lvl.strip(), msg, line), current_anchor

        # 3. Fallback: Treat as generic line inheriting timestamp
        # In implicit mode, we don't assume stack traces as aggressively
        if line.startswith(' ') or line.startswith('\t'):
            return None, current_anchor  # Treat as stack trace

        # Otherwise, new entry with inherited time
        return LogEntry(current_anchor, line_num, LogConstants.PROC_UAT,
                        LogConstants.CAT_INFO, LogConstants.LVL_DISPLAY, line,
                        line), current_anchor

    def _resolve_time(self, time_str: str, base_date: datetime) -> datetime:
        try:
            t = datetime.strptime(time_str, LogConstants.FMT_AGENT_TIME).time()
            return datetime.combine(base_date.date(), t)
        except ValueError:
            return base_date

    def _enrich_entry(self, entry: LogEntry, stats: LogStats) -> None:
        """Map/Reduce logic. Updates stats in-place."""
        # 1. Counters
        if LogConstants.LVL_ERROR in entry.level or LogConstants.LVL_ERROR in entry.message:
            stats.error_count += 1
        if LogConstants.LVL_WARNING in entry.level or LogConstants.LVL_WARNING in entry.message:
            stats.warning_count += 1

        # 2. GPU Profiling
        m_gpu = LogPatterns.GPU_PROFILE.search(entry.message)
        if m_gpu:
            cam = m_gpu.group(1)
            ms = float(m_gpu.group(2))
            entry.metadata[LogConstants.KEY_CAMERA] = cam
            entry.metadata[LogConstants.KEY_GPU_MS] = ms

            # Update Rolling Average
            total_ms = (stats.avg_gpu_ms * stats.gpu_frames_captured) + ms
            stats.gpu_frames_captured += 1
            stats.avg_gpu_ms = total_ms / stats.gpu_frames_captured

        # 3. Cook Stats
        m_cook = LogPatterns.COOK_STATS.search(entry.message)
        if m_cook:
            stats.cook_open_handles = int(m_cook.group(1))
            stats.cook_virtual_mem_mb = int(m_cook.group(2))
            entry.metadata[LogConstants.KEY_COOK_STATS] = True

        # 4. Build Outcome
        if LogPatterns.BUILD_SUCCESS.search(entry.message):
            stats.build_outcome = LogConstants.OUTCOME_SUCCESS
            entry.metadata[LogConstants.KEY_BUILD_OUTCOME] = LogConstants.OUTCOME_SUCCESS
        elif LogPatterns.BUILD_FAILURE.search(entry.message):
            stats.build_outcome = LogConstants.OUTCOME_FAILURE
            entry.metadata[LogConstants.KEY_BUILD_OUTCOME] = LogConstants.OUTCOME_FAILURE