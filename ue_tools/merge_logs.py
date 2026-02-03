from ue_tools.log_parser import LogConstants, LogParserFactory


def merge_logs(local_content, remote_content):
    """
    Parses and merges log chunks using the State-of-the-Art ue_tools parser.
    Now aligns events within a tolerance window to the same row.
    """
    # 1. Parse Local (Editor/UAT format)
    parser_local = LogParserFactory.create(LogConstants.TYPE_RUN, 'local')
    local_entries = parser_local.parse_chunk(local_content.splitlines())
    local_entries += parser_local.flush()

    # 2. Parse Remote (Agent format)
    parser_remote = LogParserFactory.create(LogConstants.TYPE_RUN, 'remote')
    remote_entries = parser_remote.parse_chunk(remote_content.splitlines())
    remote_entries += parser_remote.flush()

    # 3. Zipper Merge with Tolerance
    # Agent logs often lack milliseconds (HH:MM:SS), while UE logs are microsecond precise.
    # We use a 0.1s tolerance to ensure we catch 'same second' events.
    TOLERANCE_SECONDS = 0.1

    ui_events = []
    idx_l = 0
    idx_r = 0
    len_l = len(local_entries)
    len_r = len(remote_entries)

    while idx_l < len_l or idx_r < len_r:
        entry_l = local_entries[idx_l] if idx_l < len_l else None
        entry_r = remote_entries[idx_r] if idx_r < len_r else None

        # Determine strict chronological order first
        # Processing strategy:
        # Check if head items are close enough to merge.

        matched = False
        if entry_l and entry_r:
            delta = abs((entry_l.timestamp - entry_r.timestamp).total_seconds())
            if delta <= TOLERANCE_SECONDS:
                # Merge these two
                ui_events.append({
                    'source': 'merged',
                    'display_ts': entry_l.timestamp.strftime('%H:%M:%S'),
                    'full_ts': entry_l.timestamp,
                    'local_msg': entry_l.message,
                    'remote_msg': entry_r.message,
                })
                idx_l += 1
                idx_r += 1
                matched = True

        if not matched:
            # If not matched, process the earlier one
            if entry_l and (not entry_r or
                            entry_l.timestamp < entry_r.timestamp):
                ui_events.append({
                    'source': 'local',
                    'display_ts': entry_l.timestamp.strftime('%H:%M:%S'),
                    'full_ts': entry_l.timestamp,
                    'local_msg': entry_l.message,
                    'remote_msg': '',
                })
                idx_l += 1
            elif entry_r:
                ui_events.append({
                    'source': 'remote',
                    'display_ts': entry_r.timestamp.strftime('%H:%M:%S'),
                    'full_ts': entry_r.timestamp,
                    'local_msg': '',
                    'remote_msg': entry_r.message,
                })
                idx_r += 1

    return ui_events
