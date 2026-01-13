import re
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def parse_command_string(text: str) -> Optional[Dict[str, Any]]:
    """Parses a command string from AI response.

  Scans for the first line matching the CLI syntax: ^([A-Z_]+):\s*(.+)
  Supported commands:
  - READ_FILE: <path> [start_line]
  - SEARCH_FILE: <path> "<pattern>"
  - LIST_DIR: <path>

  Args:
    text: The raw text response from the AI.

  Returns:
    A dictionary containing 'tool' and 'args', or None if no valid command
    is found.
  """
    if not text:
        return None

    lines = text.splitlines()
    for line in lines:
        line = line.strip()
        match = re.match(r"^([A-Z_]+):\s*(.+)", line)
        if not match:
            continue

        cmd = match.group(1)
        content = match.group(2).strip()

        if cmd == "READ_FILE":
            # Syntax: READ_FILE: <path> [start_line]
            parts = content.split()
            if not parts:
                continue
            path = parts[0]
            start_line = 1
            if len(parts) > 1:
                try:
                    start_line = int(parts[1])
                except ValueError:
                    pass
            return {
                "tool": "ai_read_file",
                "args": {
                    "path": path,
                    "start_line": start_line
                }
            }

        elif cmd == "SEARCH_FILE":
            # Syntax: SEARCH_FILE: <path> "<pattern>"
            # Matches path followed by a quoted string
            m = re.match(r"^(\S+)\s+\"(.+)\"$", content)
            if m:
                return {
                    "tool": "ai_search_file",
                    "args": {
                        "path": m.group(1),
                        "pattern": m.group(2)
                    }
                }

        elif cmd == "LIST_DIR":
            # Syntax: LIST_DIR: <path>
            return {"tool": "ai_list_files", "args": {"path": content}}

    return None


def parse_ai_actions(text: str) -> list[Dict[str, Any]]:
    """Deprecated wrapper for the old parser format."""
    res = parse_command_string(text)
    return [res] if res else []
