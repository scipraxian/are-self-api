import datetime
from typing import NamedTuple

from ue_tools.log_parser import LogConstants, LogParserFactory, merge_sessions


class HydraContext(NamedTuple):
    project_root: str
    engine_root: str
    build_root: str
    staging_dir: str
    project_name: str
    dynamic_context: dict


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
    Parses and merges log chunks using the State-of-the-Art ue_tools parser.
    """
    # 1. Parse Local (Editor/UAT format)
    parser_local = LogParserFactory.create(LogConstants.TYPE_RUN, 'local')
    local_entries = parser_local.parse_chunk(local_content.splitlines())
    # Flush ensures we catch any final line
    local_entries += parser_local.flush()

    # 2. Parse Remote (Agent format)
    parser_remote = LogParserFactory.create(LogConstants.TYPE_RUN, 'remote')
    remote_entries = parser_remote.parse_chunk(remote_content.splitlines())
    remote_entries += parser_remote.flush()

    # 3. Create Session Wrappers for the Merger
    from ue_tools.log_parser import LogSession

    session_local = LogSession(entries=local_entries, source_name='local')
    session_remote = LogSession(entries=remote_entries, source_name='remote')

    # 4. Merge
    merged_session = merge_sessions(session_local, session_remote)

    # 5. Adapt to UI Format
    ui_events = []

    for entry in merged_session.entries:
        ui_events.append({
            'source': entry.source,
            'display_ts': entry.timestamp.strftime('%H:%M:%S'),
            # 'raw' contains the original line with headers, which might be preferred for debug
            # 'message' is cleaner. Let's use message to keep the UI tidy.
            'msg': entry.message,
            'full_ts': entry.timestamp
        })

    return ui_events