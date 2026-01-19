"""UE5 Log Parser utility for structured log rendering.

This module provides functionality to parse Unreal Engine 5 log files into a
structured dictionary format, suitable for downstream UI rendering. It handles
timestamps, multiline entries (like stack traces), and provide basic HTML-based
syntax highlighting for errors and warnings.
"""

import datetime
import re
from typing import Any, Dict, List

# Standard UE5 log timestamp regex: [YYYY.MM.DD-HH.MM.SS:MS]
UE5_TIMESTAMP_REGEX = re.compile(
    r'^\[(\d{4})\.(\d{2})\.(\d{2})-(\d{2})\.(\d{2})\.(\d{2}):(\d{3})\]')


def apply_log_markup(line: str) -> str:
    """Wraps log lines in HTML spans for syntax highlighting.

  Args:
    line: The raw log line string.

  Returns:
    The line wrapped in HTML spans if highlight keywords are found.
  """
    if 'Error:' in line:
        return f'<span class="error">{line}</span>'
    if 'Warning:' in line:
        return f'<span class="warning">{line}</span>'
    return line


def parse_ue5_log(
        log_content: str) -> Dict[datetime.datetime, List[Dict[str, Any]]]:
    """Parses raw UE5 log content into a structured dictionary.

  Input is a raw string of the log content. Output is a dictionary keyed by
  timestamp, grouping lines sharing that timestamp. Lines without timestamps
  are attributed to the preceding timestamp.

  Args:
    log_content: The raw string of the log content.

  Returns:
    A dictionary where:
      - Key: A datetime object representing the log entry timestamp.
      - Value: A list of dictionaries, each containing:
        - line_number (int): 1-based index from the source.
        - line_contents_raw (str): The original text content.
        - line_contents_markup (str): Text wrapped in HTML spans for basic
          syntax highlighting.
  """
    parsed_logs: Dict[datetime.datetime, List[Dict[str, Any]]] = {}
    current_timestamp = datetime.datetime.min

    if not log_content:
        return parsed_logs

    lines = log_content.splitlines()

    for i, line in enumerate(lines, start=1):
        match = UE5_TIMESTAMP_REGEX.match(line)
        if match:
            # Extract components for datetime construction
            # Groups: 1:year, 2:month, 3:day, 4:hour, 5:minute, 6:second, 7:ms
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            hour = int(match.group(4))
            minute = int(match.group(5))
            second = int(match.group(6))
            ms = int(match.group(7))

            try:
                current_timestamp = datetime.datetime(year, month, day, hour,
                                                      minute, second, ms * 1000)
            except ValueError:
                # If timestamp is invalid (e.g. 13th month), we treat it as multiline
                # for the previous valid timestamp.
                pass

        entry = {
            'line_number': i,
            'line_contents_raw': line,
            'line_contents_markup': apply_log_markup(line),
        }

        if current_timestamp not in parsed_logs:
            parsed_logs[current_timestamp] = []
        parsed_logs[current_timestamp].append(entry)

    return parsed_logs
