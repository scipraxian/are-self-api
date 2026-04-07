"""
Run shell commands in the worker (foreground or background).
"""
import subprocess
import uuid
from typing import Any, Dict, Optional

from asgiref.sync import sync_to_async

from frontal_lobe.models import ReasoningSession
from parietal_lobe.models import TerminalSession, TerminalSessionStatusID
from parietal_lobe.parietal_mcp.mcp_terminal_core import (
    detect_dangerous,
    log_path_for_session,
    popen_kwargs,
    truncate_output,
)


def _run_foreground(
    command: str,
    timeout: Optional[int],
    workdir: Optional[str],
) -> Dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
        )
        out = (completed.stdout or '') + (completed.stderr or '')
        text, truncated = truncate_output(out)
        return {
            'output': text,
            'exit_code': completed.returncode,
            'truncated': truncated,
        }
    except subprocess.TimeoutExpired as exc:
        partial = ''
        if exc.stdout:
            partial += exc.stdout.decode('utf-8', errors='replace')
        if exc.stderr:
            partial += exc.stderr.decode('utf-8', errors='replace')
        text, truncated = truncate_output(partial + '\n[Timed out]')
        return {
            'output': text,
            'exit_code': -1,
            'truncated': truncated,
        }


def _start_background(
    command: str,
    workdir: Optional[str],
    reasoning_session_id: Optional[str],
) -> Dict[str, Any]:
    session_uuid = uuid.uuid4()
    log_path = log_path_for_session(session_uuid)
    out_handle = open(log_path, 'w', encoding='utf-8')
    kwargs = popen_kwargs(workdir)
    proc = subprocess.Popen(
        command,
        shell=True,
        stdout=out_handle,
        stderr=subprocess.STDOUT,
        **kwargs,
    )
    out_handle.close()

    rs = None
    if reasoning_session_id:
        try:
            rs = ReasoningSession.objects.get(id=reasoning_session_id)
        except ReasoningSession.DoesNotExist:
            rs = None

    TerminalSession.objects.create(
        id=session_uuid,
        pid=proc.pid,
        command=command,
        workdir=workdir or '',
        status_id=TerminalSessionStatusID.RUNNING,
        reasoning_session=rs,
    )

    return {
        'pid': proc.pid,
        'session_id': str(session_uuid),
        'status': 'running',
        'log_path': log_path,
    }


async def mcp_terminal(
    command: str,
    background: bool = False,
    timeout: Optional[int] = 180,
    workdir: Optional[str] = None,
    dangerous_cmd_override: bool = False,
    session_id: str = '',
    turn_id: str = '',
) -> Dict[str, Any]:
    """Execute a shell command with optional background mode."""
    if not dangerous_cmd_override:
        reason = detect_dangerous(command)
        if reason:
            return {
                'is_dangerous': True,
                'warning': (
                    'Potentially dangerous pattern detected (%s). '
                    'Set dangerous_cmd_override=true to run anyway.' % reason
                ),
                'override_with_flag': True,
            }

    if background:
        result = await sync_to_async(_start_background)(
            command,
            workdir,
            session_id or None,
        )
        return result

    result = await sync_to_async(_run_foreground)(command, timeout, workdir)
    return result
