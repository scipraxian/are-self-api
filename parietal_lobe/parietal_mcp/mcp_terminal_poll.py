"""
Poll background shell session status and output.
"""
from typing import Any, Dict

from asgiref.sync import sync_to_async

from parietal_lobe.models import TerminalSession, TerminalSessionStatusID
from parietal_lobe.parietal_mcp.mcp_terminal_core import (
    log_path_for_session,
    process_is_running,
    read_log_tail,
)


def _poll_sync(shell_session_id: str) -> Dict[str, Any]:
    try:
        ts = TerminalSession.objects.get(id=shell_session_id)
    except TerminalSession.DoesNotExist:
        return {'ok': False, 'error': 'Unknown shell_session_id.'}

    log_path = log_path_for_session(ts.id)
    output = read_log_tail(log_path)

    if ts.status_id != TerminalSessionStatusID.RUNNING:
        return {
            'session_id': shell_session_id,
            'status': 'completed',
            'output': output,
            'pid': ts.pid,
        }

    if not process_is_running(ts.pid):
        ts.status_id = TerminalSessionStatusID.COMPLETED
        ts.stdout_buffer = output
        ts.save(update_fields=['status', 'stdout_buffer', 'modified'])
        return {
            'session_id': shell_session_id,
            'status': 'completed',
            'output': output,
            'pid': ts.pid,
        }

    return {
        'session_id': shell_session_id,
        'status': 'running',
        'output': output,
        'pid': ts.pid,
    }


async def mcp_terminal_poll(
    shell_session_id: str,
    session_id: str = '',
    turn_id: str = '',
) -> Dict[str, Any]:
    """Poll a background shell session for status and accumulated output."""
    return await sync_to_async(_poll_sync)(shell_session_id)
