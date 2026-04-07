"""
Terminate a background shell session by PID record.
"""
import os
import signal
import subprocess
import sys
from typing import Any, Dict

from asgiref.sync import sync_to_async

from parietal_lobe.models import TerminalSession, TerminalSessionStatusID
from parietal_lobe.parietal_mcp.mcp_terminal_core import process_is_running


def _kill_sync(shell_session_id: str) -> Dict[str, Any]:
    try:
        ts = TerminalSession.objects.get(id=shell_session_id)
    except TerminalSession.DoesNotExist:
        return {'ok': False, 'error': 'Unknown shell_session_id.'}

    if not process_is_running(ts.pid):
        ts.status_id = TerminalSessionStatusID.COMPLETED
        ts.save(update_fields=['status', 'modified'])
        return {'ok': True, 'session_id': shell_session_id, 'note': 'Already exited.'}

    try:
        if sys.platform == 'win32':
            subprocess.run(
                ['taskkill', '/PID', str(ts.pid), '/T', '/F'],
                capture_output=True,
                timeout=30,
            )
        else:
            os.kill(ts.pid, signal.SIGTERM)
    except OSError as exc:
        return {'ok': False, 'error': str(exc)}

    ts.status_id = TerminalSessionStatusID.KILLED
    ts.save(update_fields=['status', 'modified'])
    return {'ok': True, 'session_id': shell_session_id, 'status': 'killed'}


async def mcp_terminal_kill(
    shell_session_id: str,
    session_id: str = '',
    turn_id: str = '',
) -> Dict[str, Any]:
    """Kill a process started via mcp_terminal background mode."""
    return await sync_to_async(_kill_sync)(shell_session_id)
