"""
Execute Python in a subprocess with PYTHONPATH including the project.
"""
import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from django.conf import settings

MAX_OUT = 50 * 1024


def _code_exec_sync(code: str, timeout: int, workdir: Optional[str]) -> Dict[str, Any]:
    root = Path(settings.BASE_DIR)
    env = os.environ.copy()
    existing = env.get('PYTHONPATH', '')
    extra = str(root)
    env['PYTHONPATH'] = extra if not existing else '%s%s%s' % (
        extra,
        os.pathsep,
        existing,
    )

    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.py',
        delete=False,
        encoding='utf-8',
    ) as tmp:
        tmp.write(code)
        path = tmp.name

    try:
        completed = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir or root,
            env=env,
        )
        out = (completed.stdout or '') + (completed.stderr or '')
        truncated = len(out) > MAX_OUT
        if truncated:
            out = out[:MAX_OUT] + '\n... [truncated]'
        return {
            'stdout': completed.stdout or '',
            'stderr': completed.stderr or '',
            'exit_code': completed.returncode,
            'truncated': truncated,
            'combined_preview': out,
        }
    except subprocess.TimeoutExpired:
        return {
            'stdout': '',
            'stderr': 'Timed out.',
            'exit_code': -1,
            'truncated': False,
        }
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


async def mcp_code_exec(
    code: str,
    timeout: int = 300,
    workdir: Optional[str] = None,
    session_id: str = '',
    turn_id: str = '',
) -> Dict[str, Any]:
    """Run Python code with hermes_tools importable from PYTHONPATH."""
    return await asyncio.to_thread(_code_exec_sync, code, int(timeout), workdir)
