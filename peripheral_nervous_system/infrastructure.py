"""Infrastructure health monitoring: machine vitals and database/cache connectivity."""

import logging
import subprocess
import sys
import time

import psutil
import redis
from django.conf import settings
from django.db import connection
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def get_vitals_dict() -> dict:
    """
    Gather system vitals: CPU, RAM, disk, and GPU stats.

    Returns:
        dict: Machine vitals with CPU, RAM, disk, and optional GPU info.

    Raises:
        Exception: Caught and logged, all GPU fields set to None on failure.
    """
    # CPU metrics
    cpu_percent = psutil.cpu_percent(interval=0.1)
    cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True)
    cpu_count = psutil.cpu_count()

    # RAM metrics
    ram_info = psutil.virtual_memory()
    ram_used_gb = round(ram_info.used / (1024 ** 3), 2)
    ram_total_gb = round(ram_info.total / (1024 ** 3), 2)
    ram_percent = ram_info.percent

    # Disk metrics
    disk_path = 'C:\\' if sys.platform == 'win32' else '/'
    disk_info = psutil.disk_usage(disk_path)
    disk_used_gb = round(disk_info.used / (1024 ** 3), 2)
    disk_total_gb = round(disk_info.total / (1024 ** 3), 2)
    disk_percent = disk_info.percent

    # GPU metrics
    gpu_name = None
    gpu_utilization = None
    gpu_memory_used_mb = None
    gpu_memory_total_mb = None
    gpu_temperature = None

    try:
        result = subprocess.run(
            [
                'nvidia-smi',
                (
                    '--query-gpu=name,utilization.gpu,memory.used,'
                    'memory.total,temperature.gpu'
                ),
                '--format=csv,noheader,nounits',
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            if output:
                parts = output.split(', ')
                if len(parts) >= 5:
                    gpu_name = parts[0]
                    gpu_utilization = float(parts[1])
                    gpu_memory_used_mb = float(parts[2])
                    gpu_memory_total_mb = float(parts[3])
                    gpu_temperature = float(parts[4])
                    logger.info('[VitalSigns] GPU detected: %s', gpu_name)
                else:
                    logger.info('[VitalSigns] GPU query returned unexpected format')
        else:
            logger.info('[VitalSigns] nvidia-smi returned non-zero exit code')
    except FileNotFoundError:
        logger.info('[VitalSigns] nvidia-smi not found, GPU data unavailable')
    except subprocess.TimeoutExpired:
        logger.info('[VitalSigns] nvidia-smi timeout, GPU data unavailable')
    except Exception as e:
        logger.info('[VitalSigns] GPU detection failed: %s', str(e))

    return {
        'cpu_percent': cpu_percent,
        'cpu_per_core': cpu_per_core,
        'cpu_count': cpu_count,
        'ram_used_gb': ram_used_gb,
        'ram_total_gb': ram_total_gb,
        'ram_percent': ram_percent,
        'disk_used_gb': disk_used_gb,
        'disk_total_gb': disk_total_gb,
        'disk_percent': disk_percent,
        'gpu_name': gpu_name,
        'gpu_utilization': gpu_utilization,
        'gpu_memory_used_mb': gpu_memory_used_mb,
        'gpu_memory_total_mb': gpu_memory_total_mb,
        'gpu_temperature': gpu_temperature,
    }


def get_postgres_status() -> dict:
    """
    Probe PostgreSQL connection and gather diagnostics.

    Returns:
        dict: Connection status, version, db_size, active_connections, latency_ms.
    """
    result = {
        'connected': False,
        'version': None,
        'db_size': None,
        'active_connections': None,
        'latency_ms': None,
    }

    try:
        start = time.monotonic()
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.execute('SELECT version()')
            raw_version = cursor.fetchone()[0]
            # Extract "PostgreSQL X.Y.Z" from the full build string
            # e.g. "PostgreSQL 16.12 (Debian ...) on x86_64..." → "PostgreSQL 16.12"
            parts = raw_version.split()
            version = '%s %s' % (parts[0], parts[1]) if len(parts) >= 2 else raw_version
            cursor.execute(
                'SELECT pg_size_pretty(pg_database_size(current_database()))'
            )
            db_size = cursor.fetchone()[0]
            cursor.execute('SELECT count(*) FROM pg_stat_activity')
            active_conns = cursor.fetchone()[0]
        latency_ms = round((time.monotonic() - start) * 1000, 1)

        result['connected'] = True
        result['version'] = version
        result['db_size'] = db_size
        result['active_connections'] = active_conns
        result['latency_ms'] = latency_ms
        logger.info('[VitalSigns] PostgreSQL connected, latency=%sms', latency_ms)
    except Exception as e:
        logger.warning('[VitalSigns] PostgreSQL probe failed: %s', str(e))

    return result


def get_redis_status() -> dict:
    """
    Probe Redis connection and gather diagnostics.

    Returns:
        dict: Connection status, version, uptime_seconds, memory_used,
            connected_clients.
    """
    result = {
        'connected': False,
        'version': None,
        'uptime_seconds': None,
        'memory_used': None,
        'connected_clients': None,
    }

    try:
        broker_url = getattr(
            settings, 'CELERY_BROKER_URL', 'redis://localhost:6379/0'
        )
        r = redis.Redis.from_url(broker_url, socket_timeout=2)
        r.ping()

        info_server = r.info('server')
        info_memory = r.info('memory')
        info_clients = r.info('clients')

        result['connected'] = True
        result['version'] = info_server.get('redis_version')
        result['uptime_seconds'] = info_server.get('uptime_in_seconds')
        result['memory_used'] = info_memory.get('used_memory_human')
        result['connected_clients'] = info_clients.get('connected_clients')
        logger.info('[VitalSigns] Redis connected, version=%s', result['version'])
    except Exception as e:
        logger.warning('[VitalSigns] Redis probe failed: %s', str(e))

    return result


class VitalSignsViewSet(viewsets.ViewSet):
    """
    API to expose infrastructure health: machine vitals and service connectivity.
    """

    @action(detail=False, methods=['get'])
    def vitals(self, request):
        """
        Return machine vitals: CPU, RAM, disk, and optional GPU stats.

        Returns:
            Response: System vitals dict.
        """
        vitals = get_vitals_dict()
        return Response(vitals)

    @action(detail=False, methods=['get'])
    def status(self, request):
        """
        Probe PostgreSQL and Redis connectivity and diagnostics.

        Returns:
            Response: Dict with 'postgres' and 'redis' status dicts.
        """
        postgres_status = get_postgres_status()
        redis_status = get_redis_status()
        return Response({
            'postgres': postgres_status,
            'redis': redis_status,
        })
