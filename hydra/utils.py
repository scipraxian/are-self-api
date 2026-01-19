import re
import collections
import datetime
from datetime import datetime as dt_class

HydraContext = collections.namedtuple('HydraContext', [
    'project_root', 'engine_root', 'build_root', 'staging_dir', 'project_name',
    'dynamic_context'
])


def get_timestamp():
    return datetime.datetime.now().strftime("%H:%M:%S")


def log_system(head, message):
    entry = f"[{get_timestamp()}] {message}\n"
    head.execution_log += entry
    head.save(update_fields=['execution_log'])


def resolve_template(template_str, context: HydraContext):
    if not template_str:
        return ""
    format_data = context._asdict()
    if context.dynamic_context:
        format_data.update(context.dynamic_context)
    try:
        return template_str.format(**format_data)
    except KeyError:
        return template_str


def merge_logs(local_content, remote_content):
    """
    Parses and merges log lines. Handles UE5 and Agent timestamp formats.
    """
    events = []

    # Pattern 1: UE Standard [YYYY.MM.DD-HH.MM.SS:MS]
    ue_pattern = re.compile(r'^\[(\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{3})\]')

    # Pattern 2: Agent/Simple HH:MM:SS
    # Matches "07:44:18 [INFO]" or just "07:44:18 "
    agent_pattern = re.compile(r'^(\d{2}:\d{2}:\d{2})\s+')

    def parse_source(content, source_label):
        if not content: return

        current_entry = None

        for line in content.splitlines():
            line = line.rstrip()
            if not line: continue

            # Check UE Format
            match_ue = ue_pattern.match(line)
            if match_ue:
                ts_str = match_ue.group(1)
                try:
                    dt = dt_class.strptime(ts_str, '%Y.%m.%d-%H.%M.%S:%f')
                    display_ts = ts_str.split('-')[1]  # HH.MM.SS:MS
                    msg = re.sub(r'^\[.*?\](\[\s*\d*\])?', '', line).strip()

                    current_entry = {'full_ts': dt, 'display_ts': display_ts, 'msg': msg, 'source': source_label}
                    events.append(current_entry)
                    continue
                except ValueError:
                    pass

            # Check Agent Format
            match_agent = agent_pattern.match(line)
            if match_agent:
                time_str = match_agent.group(1)
                try:
                    # Construct a full datetime using today for sorting
                    now = datetime.datetime.now()
                    t = dt_class.strptime(time_str, '%H:%M:%S').time()
                    dt = datetime.datetime.combine(now.date(), t)

                    current_entry = {'full_ts': dt, 'display_ts': time_str, 'msg': line, 'source': source_label}
                    events.append(current_entry)
                    continue
                except ValueError:
                    pass

            # Fallback: Append to previous or create orphan
            if current_entry:
                current_entry['msg'] += f"\n{line}"
            else:
                # Use current time for orphans to ensure they appear at the end/current spot
                events.append({
                    'full_ts': datetime.datetime.now(),
                    'display_ts': '..:..:..',
                    'msg': line,
                    'source': source_label
                })

    parse_source(local_content, 'local')
    parse_source(remote_content, 'remote')

    # Sort chronologically
    events.sort(key=lambda x: x['full_ts'])
    return events