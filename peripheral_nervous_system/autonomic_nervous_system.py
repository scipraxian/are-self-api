"""Autonomic Nervous System API: control Django Celery Beat (heartbeat) via REST."""

import os
import signal
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

# PID file for the Beat process we spawn (so we can stop it from another request)
BEAT_PID_FILE = 'celery_beat.pid'


def _project_root():
    """Project root (manage.py directory)."""
    return Path(settings.BASE_DIR)


def _celery_exe():
    """Path to venv celery executable."""
    root = _project_root()
    if sys.platform == 'win32':
        return root / 'venv' / 'Scripts' / 'celery.exe'
    return root / 'venv' / 'bin' / 'celery'


def _beat_pid_path():
    return _project_root() / BEAT_PID_FILE


def _read_beat_pid():
    """Return stored Beat process PID or None."""
    path = _beat_pid_path()
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except (ValueError, OSError):
        return None


def _write_beat_pid(pid):
    path = _beat_pid_path()
    path.write_text(str(pid))


def _clear_beat_pid():
    path = _beat_pid_path()
    if path.exists():
        path.unlink(missing_ok=True)


def _is_process_running(pid):
    """Return True if a process with the given PID exists."""
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _terminate_process(pid):
    """Terminate process by PID. On Windows use taskkill for reliability."""
    if not _is_process_running(pid):
        return True
    try:
        if sys.platform == 'win32':
            # /T kills child processes too (needed when Beat is run via cmd for window title)
            subprocess.run(
                ['taskkill', '/PID', str(pid), '/F', '/T'],
                capture_output=True,
                timeout=10,
            )
        else:
            os.kill(pid, signal.SIGTERM)
        return True
    except Exception:
        return False


class CeleryBeatViewSet(viewsets.ViewSet):
    """
    API to launch and stop the Django Celery Beat server (Are-Self Heartbeat).
    Mirrors the Beat process started by talos.bat.
    """

    @action(detail=False, methods=['get'])
    def status(self, request):
        """Return whether Celery Beat is running (started by this API)."""
        pid = _read_beat_pid()
        running = _is_process_running(pid)
        if pid is not None and not running:
            _clear_beat_pid()
        return Response({
            'running': running,
            'pid': pid if running else None,
        })

    @action(detail=False, methods=['post'])
    def start(self, request):
        """Start the Celery Beat worker (same as talos.bat Are-Self Heartbeat)."""
        pid = _read_beat_pid()
        if _is_process_running(pid):
            return Response(
                {'status': 'already_running', 'pid': pid},
                status=status.HTTP_200_OK,
            )

        celery_exe = _celery_exe()
        if not celery_exe.exists():
            return Response(
                {
                    'error': 'Celery not found',
                    'path': str(celery_exe),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        cwd = _project_root()
        cmd = [
            str(celery_exe),
            '-A', 'config',
            'beat',
            '-l', 'info',
            '--scheduler', 'django_celery_beat.schedulers:DatabaseScheduler',
        ]

        try:
            if sys.platform == 'win32':
                # New console with title "Are-Self Heartbeat" (like talos.bat) and
                # stdout/stderr attached to that console so Beat logs are visible.
                title_cmd = f'title Are-Self Heartbeat && {subprocess.list2cmdline(cmd)}'
                proc = subprocess.Popen(
                    ['cmd', '/c', title_cmd],
                    cwd=str(cwd),
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            else:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(cwd),
                    start_new_session=True,
                )
            _write_beat_pid(proc.pid)
            return Response(
                {'status': 'started', 'pid': proc.pid},
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=['post'])
    def stop(self, request):
        """Stop the Celery Beat worker started via this API."""
        pid = _read_beat_pid()
        if pid is None:
            return Response(
                {'status': 'not_tracked', 'message': 'No Beat process was started by this API.'},
                status=status.HTTP_200_OK,
            )
        if not _is_process_running(pid):
            _clear_beat_pid()
            return Response(
                {'status': 'already_stopped', 'message': 'Process was not running.'},
                status=status.HTTP_200_OK,
            )
        ok = _terminate_process(pid)
        _clear_beat_pid()
        if ok:
            return Response({'status': 'stopped', 'pid': pid})
        return Response(
            {'status': 'stop_failed', 'pid': pid},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
