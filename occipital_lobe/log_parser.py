"""Generic log parser core — format-agnostic skeleton.

Owns the `LogEntry` / `LogSession` / `LogStats` data model, the
`LogParserStrategy` ABC with the shared streaming-tokenizer skeleton, and
the registry-based `LogParserFactory`. Format-specific strategies (e.g.
the Unreal Engine parsers in `ue_tools/log_parser.py`) register themselves
with the factory at module import time via `LogParserFactory.register()`.

This module intentionally knows nothing about Unreal Engine. Any consumer
that needs UE parsing must trigger `import ue_tools.log_parser` before
calling `LogParserFactory.create(LogConstants.TYPE_RUN, ...)`.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


class LogConstants(object):
    """Generic constants shared by the log parser core."""

    # Strategy type keys
    TYPE_BUILD = 'build'
    TYPE_RUN = 'run'

    # Sources
    SOURCE_UNKNOWN = 'unknown'

    # Outcomes
    OUTCOME_SUCCESS = 'SUCCESS'
    OUTCOME_FAILURE = 'FAILURE'

    # Date Formats
    FMT_AGENT_TIME = '%H:%M:%S'

    # Categories
    CAT_INFO = 'Info'

    # Levels
    LVL_DISPLAY = 'Display'
    LVL_ERROR = 'Error'
    LVL_WARNING = 'Warning'


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
    """Abstract Base Class for stateful log parsing strategies.

    Subclasses implement `parse_chunk()` and may override `_enrich_entry()`
    to add format-specific post-processing (pattern matches, metadata
    extraction). The base `_enrich_entry()` handles generic error/warning
    counting only — subclasses should call `super()._enrich_entry(entry)`.
    """

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
        """Generic enrichment: error/warning counters. Subclasses extend."""
        if LogConstants.LVL_ERROR in entry.level or LogConstants.LVL_ERROR in entry.message:
            self.stats.error_count += 1
        if LogConstants.LVL_WARNING in entry.level or LogConstants.LVL_WARNING in entry.message:
            self.stats.warning_count += 1

    def _resolve_agent_time(self, time_str: str) -> datetime:
        try:
            t = datetime.strptime(time_str, LogConstants.FMT_AGENT_TIME).time()
            return datetime.combine(self.current_timestamp.date(), t)
        except ValueError:
            return self.current_timestamp


class LogParserFactory(object):
    """Registry-based factory for log parser strategies.

    Format plugins register their strategies at module import time:

        LogParserFactory.register(LogConstants.TYPE_RUN, UERunLogStrategy)

    Callers then request a strategy by type key:

        parser = LogParserFactory.create(LogConstants.TYPE_RUN, 'local')
    """

    _registry: Dict[str, type] = {}

    @classmethod
    def register(cls, log_type: str, strategy_cls: type) -> None:
        cls._registry[log_type] = strategy_cls

    @classmethod
    def create(cls, log_type: str, source_label: str) -> LogParserStrategy:
        strategy_cls = cls._registry.get(log_type)
        if strategy_cls is None:
            raise ValueError(f'Unknown log type: {log_type}')
        return strategy_cls(source_name=source_label)


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
