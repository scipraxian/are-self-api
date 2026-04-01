"""N-way correlated timeline merge for spike logs."""

import heapq
import logging
from dataclasses import dataclass, field
from datetime import datetime

from ue_tools.log_parser import LogConstants, LogEntry, LogParserFactory

logger = logging.getLogger(__name__)

TOLERANCE_SECONDS = 0.1
DISPLAY_TS_FORMAT = '%H:%M:%S'


@dataclass
class MergedRow:
    """A single row in the correlated timeline."""

    timestamp: str
    full_ts: datetime
    columns: dict = field(default_factory=dict)
    source: list = field(default_factory=list)


@dataclass
class NWayMergeResult:
    """Result container for the N-way merge."""

    labels: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    cursors: dict = field(default_factory=dict)


def _parse_log_content(
    label: str, content: str
) -> list[LogEntry]:
    """Parse log content through the standard run strategy."""
    parser = LogParserFactory.create(LogConstants.TYPE_RUN, label)
    entries = parser.parse_chunk(content.splitlines())
    entries += parser.flush()
    return entries


def _build_sorted_entries(
    sources: list[tuple[str, str]]
) -> list[tuple[datetime, int, str, LogEntry]]:
    """Parse all sources and return a heap-sorted list of entries."""
    heap: list[tuple[datetime, int, str, LogEntry]] = []
    counter = 0

    for label, content in sources:
        if not content:
            continue
        entries = _parse_log_content(label, content)
        for entry in entries:
            heapq.heappush(
                heap, (entry.timestamp, counter, label, entry)
            )
            counter += 1

    sorted_entries = []
    while heap:
        sorted_entries.append(heapq.heappop(heap))

    return sorted_entries


def _group_into_rows(
    sorted_entries: list[tuple[datetime, int, str, LogEntry]],
    labels: list[str]
) -> list[MergedRow]:
    """Group sorted entries into rows using tolerance window."""
    rows: list[MergedRow] = []

    for ts, _counter, label, entry in sorted_entries:
        grouped = False
        if rows:
            last_row = rows[-1]
            delta = abs(
                (ts - last_row.full_ts).total_seconds()
            )
            if (delta <= TOLERANCE_SECONDS
                    and not last_row.columns.get(label)):
                last_row.columns[label] = entry.message
                last_row.source.append(label)
                grouped = True

        if not grouped:
            columns = {lbl: '' for lbl in labels}
            columns[label] = entry.message
            rows.append(MergedRow(
                timestamp=ts.strftime(DISPLAY_TS_FORMAT),
                full_ts=ts,
                columns=columns,
                source=[label],
            ))

    return rows


def merge_logs_nway(
    sources: list[tuple[str, str]]
) -> NWayMergeResult:
    """Merge N spike logs into a correlated columnar timeline.

    Args:
        sources: list of (label, log_content) tuples. 2-4 expected.

    Returns:
        NWayMergeResult with labels, merged rows, and cursors.
    """
    labels = [label for label, _ in sources]
    logger.info(
        '[MergeLogs] N-way merge started. Sources: %s', labels
    )

    sorted_entries = _build_sorted_entries(sources)
    rows = _group_into_rows(sorted_entries, labels)

    cursors = {}
    for label, content in sources:
        cursors[label] = len(content) if content else 0

    logger.info(
        '[MergeLogs] Merge complete. %d rows produced.', len(rows)
    )

    return NWayMergeResult(
        labels=labels,
        rows=rows,
        cursors=cursors,
    )


def merge_delta(
    chunks: list[tuple[str, str]]
) -> NWayMergeResult:
    """Merge only new delta chunks into incremental rows.

    Same algorithm as merge_logs_nway but intended for partial
    content received since the last cursor position.

    Args:
        chunks: list of (label, delta_content) tuples.

    Returns:
        NWayMergeResult with only the new rows.
    """
    return merge_logs_nway(chunks)


def serialize_row(row: MergedRow) -> dict:
    """Convert a MergedRow to a JSON-safe dictionary."""
    return {
        'timestamp': row.timestamp,
        'full_ts': row.full_ts.isoformat(),
        'columns': row.columns,
        'source': row.source,
    }


def serialize_result(
    result: NWayMergeResult, any_active: bool = False
) -> dict:
    """Convert NWayMergeResult to the API response shape."""
    return {
        'labels': result.labels,
        'rows': [serialize_row(r) for r in result.rows],
        'cursors': result.cursors,
        'any_active': any_active,
    }
