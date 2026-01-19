import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional


@dataclass
class LogEntry:
    timestamp: datetime
    line_num: int
    process: str
    category: str
    level: str
    message: str
    raw: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class LogIngestor(object):

    def __init__(self):
        # Anchor: Log started at 1/8/2026 10:13:29 AM
        self.re_anchor_start = re.compile(
            r"Log started at (\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}:\d{2} [AP]M)")
        # Also handle ISO format if it appears: (2026-01-08T18:13:29Z) - usually purely informational in brackets, may not need direct parsing if "Log started at" covers it.

        # Standard UE: [2026.01.08-10.13.34:123]LogCook: Display: ...
        self.re_standard = re.compile(
            r"^\[(\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{3})\]\s*([^:]+):\s*([^:]+):\s*(.*)"
        )

        # Agent: 10:13:29 [INFO] ...
        self.re_agent = re.compile(
            r"^(\d{2}:\d{2}:\d{2})\s+\[([^\]]+)\]\s+(.*)")

        # UAT: LogCook: Display: ... (No timestamp)
        # Groups: Category, Level, Message
        self.re_uat = re.compile(r"^([a-zA-Z0-9_]+):\s*([a-zA-Z0-9_]+):\s*(.*)")

        # Metadata Patterns
        self.re_cook_diag = re.compile(
            r"OpenFileHandles=(\d+).*VirtualMemory=(\d+)MiB")

        self.entries: List[LogEntry] = []
        self._last_timestamp: Optional[datetime] = None

    def parse(self, log_lines: List[str]) -> List[LogEntry]:
        self.entries = []
        self._last_timestamp = None

        for idx, line in enumerate(log_lines):
            line_num = idx + 1
            original_line = line.strip('\r\n')
            if not original_line:
                continue

            entry = self._parse_line(original_line, line_num)

            if entry:
                self.entries.append(entry)
                self._last_timestamp = entry.timestamp
            else:
                # Stack Trace Recovery
                if self.entries:
                    self.entries[-1].message += "\n" + original_line
                    self.entries[-1].raw += "\n" + original_line
                else:
                    # If we have no entries yet (start of file garbage), we check if it's a known non-log marker we want to keep?
                    # But per spec, we only append to previous valid entry. If none, we discard or wait.
                    # However, first line usually is valid.
                    pass

        return self.entries

    def _parse_line(self, line: str, line_num: int) -> Optional[LogEntry]:
        # 1. Check Anchor
        m_anchor = self.re_anchor_start.search(line)
        if m_anchor:
            dt_str = m_anchor.group(1)
            try:
                # 1/8/2026 10:13:29 AM
                dt = datetime.strptime(dt_str, "%m/%d/%Y %I:%M:%S %p")
                return self._create_entry(dt, line_num, "UAT", "LogInit",
                                          "Display", line, line)
            except ValueError:
                pass

        # 2. Check Standard UE
        m_std = self.re_standard.match(line)
        if m_std:
            ts_str, category, level, msg = m_std.groups()
            try:
                dt = datetime.strptime(ts_str, "%Y.%m.%d-%H.%M.%S:%f")
                return self._create_entry(dt, line_num, "Editor",
                                          category.strip(), level.strip(), msg,
                                          line)
            except ValueError:
                pass

        # 3. Check Agent
        m_agent = self.re_agent.match(line)
        if m_agent:
            time_str, level_in_brackets, msg = m_agent.groups()
            # Inherit date
            dt = self._resolve_time(time_str, has_date=False)
            return self._create_entry(dt, line_num, "Agent", "AgentLog",
                                      level_in_brackets.strip(), msg, line)

        # 4. Check UAT (No TS) - stricter to avoid matching normal sentences 'Word: Word: ...'
        # But UAT logs are usually strict.
        m_uat = self.re_uat.match(line)
        if m_uat:
            category, level, msg = m_uat.groups()
            # Inherit full timestamp
            dt = self._resolve_time(None, has_date=False)
            return self._create_entry(dt, line_num, "UAT", category.strip(),
                                      level.strip(), msg, line)

        # 5. Explicit Build Status (Forensic)
        if "BUILD SUCCESSFUL" in line or "BUILD FAILED" in line:
            dt = self._resolve_time(None)
            return self._create_entry(dt, line_num, "System", "BuildStatus",
                                      "Display", line, line)

        return None

    def _resolve_time(self,
                      time_str: Optional[str] = None,
                      has_date: bool = False) -> datetime:
        if has_date and time_str:
            # Not used currently as we parse full TS in regex
            return datetime.now()

        last = self._last_timestamp if self._last_timestamp else datetime.now()

        if time_str:
            # Parse time only, apply to last date
            try:
                t = datetime.strptime(time_str, "%H:%M:%S").time()
                return datetime.combine(last.date(), t)
            except ValueError:
                return last

        return last

    def _create_entry(self, dt: datetime, line_num: int, process: str,
                      category: str, level: str, message: str,
                      raw: str) -> LogEntry:
        meta = self._extract_metadata(message)
        # Create entry
        return LogEntry(dt, line_num, process, category, level, message, raw,
                        meta)

    def _extract_metadata(self, message: str) -> Dict[str, Any]:
        meta = {}

        # GPU
        # Check for signature instead of "PROFILEGPU" (which might be consumed as level)
        if "total GPU time" in message:
            # Pattern: MainMenuPerfCam (1280x720): total GPU time 12.54 ms
            m_gpu = re.search(
                r"([\w]+)\s*\(.*?\):\s*total GPU time\s*([\d\.]+)\s*ms",
                message)
            if m_gpu:
                cam, ms = m_gpu.groups()
                meta['camera'] = cam
                meta['gpu_ms'] = float(ms)

        # Cook
        if "Cook Diagnostics" in message:
            m_cook = self.re_cook_diag.search(message)
            if m_cook:
                handles, mem = m_cook.groups()
                meta['open_file_handles'] = int(handles)
                meta['virtual_memory_mb'] = int(mem)

        # Build Outcome
        if "BUILD SUCCESSFUL" in message:
            meta['build_outcome'] = "SUCCESS"
        if "BUILD FAILED" in message:
            meta['build_outcome'] = "FAILURE"

        return meta
