# [file: talos_frontal/utils.py]
import re
import logging
import json
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def parse_command_string(text: str) -> Optional[Dict[str, Any]]:
    """Parses a command string from AI response.

  Scans for:
  1. CLI Syntax: ^([A-Z_]+):\s*(.+)
  2. Legacy/Direct Syntax: :::tool(...) ::: or just tool(...)

  Args:
    text: The raw text response from the AI.

  Returns:
    A dictionary containing 'tool' and 'args', or None.
  """
    if not text:
        return None

    lines = text.splitlines()
    for line in lines:
        line = line.strip()

        # --- STRATEGY 1: STRICT CLI (Preferred) ---
        match_cli = re.match(r"^([A-Z_]+):\s*(.+)", line)
        if match_cli:
            cmd = match_cli.group(1)
            content = match_cli.group(2).strip()

            if cmd == "READ_FILE":
                parts = content.split()
                path = parts[0]
                start_line = 1
                if len(parts) > 1:
                    try:
                        start_line = int(parts[1])
                    except ValueError:
                        pass
                return {
                    "tool": "ai_read_file",
                    "args": {"path": path, "start_line": start_line}
                }

            elif cmd == "SEARCH_FILE":
                m = re.match(r"^(\S+)\s+\"(.+)\"$", content)
                if m:
                    return {
                        "tool": "ai_search_file",
                        "args": {"path": m.group(1), "pattern": m.group(2)}
                    }
                # Fallback for lazy quotes
                parts = content.split(" ", 1)
                if len(parts) == 2:
                    return {
                        "tool": "ai_search_file",
                        "args": {"path": parts[0], "pattern": parts[1].strip('"')}
                    }

            elif cmd == "LIST_DIR":
                return {"tool": "ai_list_files", "args": {"path": content.strip('"')}}

        # --- STRATEGY 2: DIRECT CALL (The "Small Model" Fallback) ---
        # Matches: ai_read_file(path='...') or :::ai_read_file(...) :::
        # We look for the tool name followed by parentheses
        match_direct = re.search(r"(ai_\w+)\((.+)\)", line)
        if match_direct:
            tool_name = match_direct.group(1)
            args_str = match_direct.group(2)

            args = {}

            # 1. Try naive regex parsing for common kwargs
            # path='foo' or path="foo"
            path_match = re.search(r"path=['\"]([^'\"]+)['\"]", args_str)
            if path_match:
                args['path'] = path_match.group(1)

            # start_line=1
            line_match = re.search(r"start_line=(\d+)", args_str)
            if line_match:
                args['start_line'] = int(line_match.group(1))

            # pattern='foo'
            pat_match = re.search(r"pattern=['\"]([^'\"]+)['\"]", args_str)
            if pat_match:
                args['pattern'] = pat_match.group(1)

            # If regex failed to find path, maybe it's positional? "ai_read_file('foo')"
            if 'path' not in args:
                pos_match = re.match(r"^['\"]([^'\"]+)['\"]", args_str)
                if pos_match:
                    args['path'] = pos_match.group(1)

            if tool_name in ['ai_read_file', 'ai_search_file', 'ai_list_files'] and 'path' in args:
                return {"tool": tool_name, "args": args}

    return None


def parse_ai_actions(text: str) -> list[Dict[str, Any]]:
    """Deprecated wrapper."""
    res = parse_command_string(text)
    return [res] if res else []