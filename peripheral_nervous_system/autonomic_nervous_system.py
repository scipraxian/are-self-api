"""Autonomic Nervous System API: control Django Celery Beat (heartbeat) via REST."""

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from config.celery import app as celery_app

logger = logging.getLogger(__name__)

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
    Mirrors the Beat process started by are_self.bat.
    """

    @action(detail=False, methods=['get'])
    def status(self, request):
        """Return Beat status plus scheduled periodic tasks."""
        from django_celery_beat.models import PeriodicTask

        pid = _read_beat_pid()
        running = _is_process_running(pid)
        if pid is not None and not running:
            _clear_beat_pid()

        tasks = []
        for pt in PeriodicTask.objects.filter(enabled=True).order_by('name'):
            schedule_str = ''
            if pt.interval:
                schedule_str = f'every {pt.interval.every} {pt.interval.period}'
            elif pt.crontab:
                schedule_str = f'{pt.crontab.minute} {pt.crontab.hour} {pt.crontab.day_of_week}'

            tasks.append({
                'name': pt.name,
                'task': pt.task,
                'schedule': schedule_str,
                'total_run_count': pt.total_run_count,
                'last_run_at': pt.last_run_at.isoformat() if pt.last_run_at else None,
            })

        return Response({
            'running': running,
            'pid': pid if running else None,
            'scheduled_tasks': tasks,
        })

    @action(detail=False, methods=['post'])
    def start(self, request):
        """Start the Celery Beat worker (same as are_self.bat Are-Self Heartbeat)."""
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
                # New console with title "Are-Self Heartbeat" (like are_self.bat) and
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


class CeleryWorkerViewSet(viewsets.ViewSet):
    """API to inspect active Celery workers and their current tasks."""

    def list(self, request):
        """Return active Celery workers and their current tasks."""
        inspect = celery_app.control.inspect()

        try:
            active = inspect.active() or {}
            stats = inspect.stats() or {}
            reserved = inspect.reserved() or {}
        except Exception:
            logger.exception('[PNS] Could not reach Celery workers.')
            return Response(
                {'error': 'Could not reach workers'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        workers = []
        for hostname, tasks in active.items():
            worker_stats = stats.get(hostname, {})
            worker_reserved = reserved.get(hostname, [])
            workers.append({
                'hostname': hostname,
                'active_tasks': tasks,
                'reserved_tasks': worker_reserved,
                'pool': worker_stats.get('pool', {}),
                'broker': worker_stats.get('broker', {}),
                'prefetch_count': worker_stats.get(
                    'prefetch_count', 0
                ),
                'rusage': worker_stats.get('rusage', {}),
                'total': worker_stats.get('total', {}),
                'pid': worker_stats.get('pid'),
            })

        return Response({'workers': workers})


def delayed_shutdown() -> None:
    """Background thread to kill the Django process after returning the HTTP
    response.
    """
    time.sleep(1.0)
    os._exit(0)


def delayed_restart() -> None:
    """Background thread to restart Celery worker and exit Django process."""
    time.sleep(1.0)
    os._exit(0)


class SystemControlViewSet(viewsets.ViewSet):
    """API to control system shutdown, restart, and status."""

    permission_classes = [AllowAny]

    @action(detail=False, methods=['post'])
    def shutdown(self, request) -> Response:
        """Shutdown Celery workers and the Django process."""
        logger.info('[PNS] System shutdown initiated.')
        # 1. Send shutdown broadcast to Celery workers
        celery_app.control.shutdown()

        # 2. Spawn a delayed thread to kill the Django process
        threading.Thread(target=delayed_shutdown).start()

        return Response(
            {'status': 'System shutdown initiated'},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'])
    def restart(self, request) -> Response:
        """Restart Celery worker and Django process."""
        logger.info('[PNS] System restart initiated.')
        # 1. Shutdown Celery workers
        celery_app.control.shutdown()

        # 2. Restart Celery worker via subprocess
        cwd = _project_root()
        cmd = [
            sys.executable,
            '-m',
            'celery',
            '-A',
            'config',
            'worker',
            '-l',
            'info',
            '--pool=solo',
        ]

        try:
            if sys.platform == 'win32':
                # Windows: use CREATE_NEW_CONSOLE to spawn in new window
                title_cmd = (
                    'title Are-Self Worker && '
                    f'{subprocess.list2cmdline(cmd)}'
                )
                subprocess.Popen(
                    ['cmd', '/c', title_cmd],
                    cwd=str(cwd),
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            else:
                # Unix: start new session
                subprocess.Popen(
                    cmd,
                    cwd=str(cwd),
                    start_new_session=True,
                )
            logger.info('[PNS] Celery worker restart process spawned.')
        except Exception as e:
            logger.exception(
                '[PNS] Failed to spawn Celery worker: %s', str(e)
            )

        # 3. Check if Beat is running and restart it
        beat_pid = _read_beat_pid()
        if _is_process_running(beat_pid):
            logger.info('[PNS] Restarting Celery Beat.')
            _terminate_process(beat_pid)
            _clear_beat_pid()

            # Restart Beat
            celery_exe = _celery_exe()
            if celery_exe.exists():
                beat_cmd = [
                    str(celery_exe),
                    '-A',
                    'config',
                    'beat',
                    '-l',
                    'info',
                    '--scheduler',
                    'django_celery_beat.schedulers:DatabaseScheduler',
                ]
                try:
                    if sys.platform == 'win32':
                        beat_title = (
                            'title Are-Self Heartbeat && '
                            f'{subprocess.list2cmdline(beat_cmd)}'
                        )
                        beat_proc = subprocess.Popen(
                            ['cmd', '/c', beat_title],
                            cwd=str(cwd),
                            creationflags=subprocess.CREATE_NEW_CONSOLE,
                        )
                    else:
                        beat_proc = subprocess.Popen(
                            beat_cmd,
                            cwd=str(cwd),
                            start_new_session=True,
                        )
                    _write_beat_pid(beat_proc.pid)
                    logger.info(
                        '[PNS] Celery Beat restarted with PID %s.',
                        beat_proc.pid,
                    )
                except Exception as e:
                    logger.exception('[PNS] Failed to restart Beat: %s',
                                     str(e))

        # 4. Spawn delayed thread to kill Django process
        threading.Thread(target=delayed_restart).start()

        return Response(
            {'status': 'System restart initiated'},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['get'])
    def status(self, request) -> Response:
        """Return system status: workers online, Beat running, and uptime."""
        inspect = celery_app.control.inspect()
        workers_online = 0

        try:
            stats = inspect.stats() or {}
            workers_online = len(stats)
        except Exception:
            logger.warning('[PNS] Could not inspect Celery workers.')

        beat_pid = _read_beat_pid()
        beat_running = _is_process_running(beat_pid)

        # Clean up stale Beat PID if process is gone
        if beat_pid is not None and not beat_running:
            _clear_beat_pid()

        return Response({
            'workers_online': workers_online,
            'beat_running': beat_running,
            'timestamp': timezone.now().isoformat(),
        })
