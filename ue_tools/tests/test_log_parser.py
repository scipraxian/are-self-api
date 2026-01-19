"""Tests for the UE5 Log Parser utility."""

import datetime
import os
from ue_tools.log_parser import parse_ue5_log


def test_standard_line():
    """Verify a standard log line parses into the correct key and values."""
    log = "[2026.01.18-12.00.00:123]LogInit: Display: Hello"
    parsed = parse_ue5_log(log)
    expected_ts = datetime.datetime(2026, 1, 18, 12, 0, 0, 123000)
    assert expected_ts in parsed
    assert len(parsed[expected_ts]) == 1
    assert parsed[expected_ts][0]['line_contents_raw'] == log
    assert parsed[expected_ts][0]['line_number'] == 1


def test_timestamp_collision():
    """Verify multiple lines with the same timestamp appear under the same key."""
    log = ("[2026.01.18-12.00.00:123]Line 1\n"
           "[2026.01.18-12.00.00:123]Line 2")
    parsed = parse_ue5_log(log)
    expected_ts = datetime.datetime(2026, 1, 18, 12, 0, 0, 123000)
    assert len(parsed[expected_ts]) == 2
    assert parsed[expected_ts][0][
        'line_contents_raw'] == "[2026.01.18-12.00.00:123]Line 1"
    assert parsed[expected_ts][1][
        'line_contents_raw'] == "[2026.01.18-12.00.00:123]Line 2"


def test_stack_trace_multiline():
    """Verify lines without timestamps are grouped under the preceding key."""
    log = ("[2026.01.18-12.00.00:123]First line\n"
           "Stack trace line 1\n"
           "Stack trace line 2")
    parsed = parse_ue5_log(log)
    expected_ts = datetime.datetime(2026, 1, 18, 12, 0, 0, 123000)
    assert len(parsed[expected_ts]) == 3
    assert parsed[expected_ts][0][
        'line_contents_raw'] == "[2026.01.18-12.00.00:123]First line"
    assert parsed[expected_ts][1]['line_contents_raw'] == "Stack trace line 1"
    assert parsed[expected_ts][2]['line_contents_raw'] == "Stack trace line 2"


def test_markup():
    """Verify Error: and Warning: produce the correct HTML span classes."""
    log = ("LogInit: Error: Something went wrong\n"
           "LogInit: Warning: Just checking")
    parsed = parse_ue5_log(log)
    # Orphans go to datetime.min
    ts = datetime.datetime.min
    assert '<span class="error">' in parsed[ts][0]['line_contents_markup']
    assert '<span class="warning">' in parsed[ts][1]['line_contents_markup']


def test_empty_input():
    """Handle empty strings gracefully."""
    assert parse_ue5_log("") == {}


def test_uat_real_log_file():
    """Verify parsing of the real UAT log file provided."""
    log_path = os.path.join(os.path.dirname(__file__), 'test_uat_build_log.txt')

    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    parsed = parse_ue5_log(content)

    # The provided log file doesn't seem to have [YYYY.MM.DD-HH.MM.SS:MS]
    # formatted timestamps (checked via grep), so they should all be orphans.
    assert datetime.datetime.min in parsed
    # Verify we captured all lines (roughly 1885 expected from previous view_file)
    total_lines = sum(len(lines) for lines in parsed.values())
    assert total_lines > 1800

    # Check for some known content to ensure it's not totally broken
    found_success = False
    for entry in parsed[datetime.datetime.min]:
        if 'BUILD SUCCESSFUL' in entry['line_contents_raw']:
            found_success = True
            break
    assert found_success
