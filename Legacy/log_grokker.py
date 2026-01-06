"""UE session log analyzer and visualizer.

This script parses aggregated Unreal Engine logs from both host and remote
sessions, filters for interesting events, and generates a synchronized
timeline-style HTML view.
"""

import logging
import os
import re
import sys
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

# CONFIGURATION
# -----------------------------------------------------------------------------
INTERESTING_CATEGORIES = [
    'LogBlueprintUserMessages',
    'LogNet',
    'LogWorldPartition',
    'LogScript',
    'LogTemp',
    'LogOnlineSession',
    'LogGameMode',
    'LogGameState',
    'LogPlayerController'
]

INTERESTING_KEYWORDS = [
    'Error:',
    'Warning:',
    'Possessed',
    'Unpossessed',
    'Server_TargetActorCounter',
    'OnRep_',
    'Client_SafeInit',
    'BeginPlay',
    'Steam Group',
    'Hero',
    'L_HSH_Hotel'
]


# -----------------------------------------------------------------------------

def parse_log_section(content, label):
    """Parses a raw log block into a list of event dictionaries.

    Args:
        content (str): The raw log content to parse.
        label (str): The source label ('HOST' or 'REMOTE').

    Returns:
        list[dict]: A list of event dictionaries with timestamp, category, etc.
    """
    events = []
    # Regex to catch the standard UE timestamp: [2026.01.02-13.07.47:881]
    timestamp_pattern = re.compile(
        r'^\[(\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{3})\]'
    )
    category_pattern = re.compile(r'\]\[\s*\d*\](\w+):')

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue

        match = timestamp_pattern.match(line)
        if match:
            time_str = match.group(1)
            try:
                dt_object = datetime.strptime(time_str, '%Y.%m.%d-%H.%M.%S:%f')
            except ValueError:
                continue

            cat_match = category_pattern.search(line)
            category = cat_match.group(1) if cat_match else 'Unknown'

            is_interesting = category in INTERESTING_CATEGORIES
            if not is_interesting:
                for kw in INTERESTING_KEYWORDS:
                    if kw in line:
                        is_interesting = True
                        break

            if is_interesting:
                clean_msg = re.sub(r'^\[.*?\]\[\s*\d*\]', '', line)
                events.append({
                    'timestamp': dt_object,
                    'time_display': time_str.split('-')[1],
                    'source': label,
                    'category': category,
                    'message': clean_msg
                })
    return events


def generate_html(events, output_filename):
    """Generates a Timeline-style HTML view.

    Args:
        events (list[dict]): Sorted list of event dictionaries.
        output_filename (str): Path to write the HTML file.
    """
    html_header = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>HSH Session Timeline</title>
        <style>
            body { background-color: #121212; color: #e0e0e0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-size: 13px; margin: 0; padding: 20px; }
            .timeline { display: flex; flex-direction: column; gap: 4px; max-width: 1800px; margin: 0 auto; }

            /* The Row: Holds Host (Left) | Time (Center) | Remote (Right) */
            .row { display: flex; align-items: flex-start; }

            .col-host { flex: 1; text-align: right; padding-right: 15px; border-right: 2px solid #333; }
            .col-time { width: 100px; text-align: center; font-weight: bold; color: #569cd6; font-family: monospace; padding-top: 2px; }
            .col-remote { flex: 1; text-align: left; padding-left: 15px; border-left: 2px solid #333; margin-left: -2px; }

            .msg-box { padding: 4px 8px; border-radius: 4px; display: inline-block; max-width: 95%; word-wrap: break-word; }

            /* Specific Styling based on content */
            .host-msg { background-color: #1e1e1e; color: #d4d4d4; }
            .remote-msg { background-color: #0d1117; color: #c9d1d9; }

            .category { font-size: 0.85em; color: #808080; display: block; margin-bottom: 2px; }

            .bp-msg { color: #4ec9b0; }
            .net-msg { color: #c586c0; }
            .warning { color: #dcdcaa; border-left: 3px solid #dcdcaa; }
            .error { color: #f44747; border-left: 3px solid #f44747; }
        </style>
    </head>
    <body>
        <div style="text-align: center; margin-bottom: 20px; color: #888;">
            <h1>HSH Session Timeline</h1>
            <div style="display:flex; justify-content:center; gap:50px;">
                <h2 style="color:#d4d4d4;">HOST (Local)</h2>
                <h2 style="color:#c9d1d9;">REMOTE (Client)</h2>
            </div>
        </div>
        <div class="timeline">
    """

    body_rows = []
    for e in events:
        msg_class = ''
        style_class = ''

        if 'LogBlueprintUserMessages' in e['category']:
            msg_class = 'bp-msg'
        elif 'LogNet' in e['category']:
            msg_class = 'net-msg'

        if 'Warning' in e['message']:
            style_class = 'warning'
        elif 'Error' in e['message']:
            style_class = 'error'

        # Build the message block
        content = (
            f'<div class="msg-box {style_class} '
            f'{"host-msg" if e["source"] == "HOST" else "remote-msg"}">'
            f'<span class="category">{e["category"]}</span>'
            f'<span class="{msg_class}">{e["message"]}</span>'
            '</div>'
        )

        row = '<div class="row">'
        if e['source'] == 'HOST':
            row += f'<div class="col-host">{content}</div>'
            row += f'<div class="col-time">{e["time_display"]}</div>'
            row += '<div class="col-remote"></div>'
        else:
            row += '<div class="col-host"></div>'
            row += f'<div class="col-time">{e["time_display"]}</div>'
            row += f'<div class="col-remote">{content}</div>'
        row += '</div>'
        body_rows.append(row)

    html_footer = """
        </div>
    </body>
    </html>
    """

    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(html_header)
            f.write('\n'.join(body_rows))
            f.write(html_footer)
        logger.info('Successfully generated: %s', output_filename)
    except IOError as e:
        logger.error('Failed to write HTML file: %s', e)


def main():
    """Main entry point for log grokker script."""
    if len(sys.argv) < 2:
        logger.error('Usage: python log_grokker.py <logfile.log>')
        return

    filename = sys.argv[1]
    if not os.path.exists(filename):
        logger.error('File not found: %s', filename)
        return

    try:
        with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
            full_content = f.read()
    except IOError as e:
        logger.error('Failed to read log file: %s', e)
        return

    host_header = '=== LOCAL CLIENT LOG (Host) ==='
    remote_header = '=== REMOTE AGENT LOG'

    host_start = full_content.rfind(host_header)
    remote_start = full_content.rfind(remote_header)

    if host_start == -1 or remote_start == -1:
        logger.error('Error: Could not find Host or Remote log headers.')
        return

    if host_start < remote_start:
        host_content = full_content[host_start:remote_start]
        remote_content = full_content[remote_start:]
    else:
        remote_content = full_content[remote_start:host_start]
        host_content = full_content[host_start:]

    logger.info('Parsing Host Log (%d chars)...', len(host_content))
    host_events = parse_log_section(host_content, 'HOST')

    logger.info('Parsing Remote Log (%d chars)...', len(remote_content))
    remote_events = parse_log_section(remote_content, 'REMOTE')

    all_events = host_events + remote_events
    all_events.sort(key=lambda x: x['timestamp'])

    output_html = filename + '.html'
    generate_html(all_events, output_html)


if __name__ == '__main__':
    # Configure basic logging for the script
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )
    main()