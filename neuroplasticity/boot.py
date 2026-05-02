"""Deferred boot hook for NeuralModifier genomes.

Django 6.x raises ``RuntimeWarning: Accessing the database during app
initialization is discouraged.`` whenever an ORM query fires inside
``AppConfig.ready()`` (or anywhere on the module-import path). The boot
pass in ``loader.boot_genomes()`` reads ``NeuralModifier`` rows to
decide which genomes to put on ``sys.path``, so running it straight
from ``NeuroplasticityConfig.ready()`` trips the warning every time
the process starts.

This module shims that off the ready path. ``schedule_boot()`` is
called from ``ready()``; it connects one-shot receivers to
``django.core.signals.request_started`` (covers Daphne / runserver /
any HTTP-facing process) and ``celery.signals.worker_ready`` (covers
Celery workers). The first receiver to fire runs ``boot_genomes()``
and disconnects both — a module-level flag guards against any double
fire inside the same process.

Test, ``migrate``, and ``makemigrations`` paths don't reach here at
all — ``NeuroplasticityConfig.ready()`` short-circuits before calling
``schedule_boot()`` for those, and tests that need the boot pass call
``loader.boot_genomes()`` directly (see
``test_modifier_lifecycle.py``).
"""

from __future__ import annotations

import logging
import threading

from django.core.signals import request_started

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_booted = False


def schedule_boot() -> None:
    """Connect one-shot receivers that run ``boot_genomes`` post-ready.

    Safe to call multiple times — subsequent calls are no-ops once
    ``_booted`` flips. ``weak=False`` pins the receivers so they stay
    alive even if nothing else holds a reference.
    """
    request_started.connect(_on_request_started, weak=False)

    try:
        from celery.signals import worker_ready
    except ImportError:
        # Celery not installed in this process tree — request_started
        # alone is sufficient.
        return
    worker_ready.connect(_on_worker_ready, weak=False)


def _on_request_started(sender, **kwargs) -> None:
    try:
        request_started.disconnect(_on_request_started)
    except Exception:
        pass
    _run_once()


def _on_worker_ready(sender, **kwargs) -> None:
    try:
        from celery.signals import worker_ready
        worker_ready.disconnect(_on_worker_ready)
    except Exception:
        pass
    _run_once()


def _run_once() -> None:
    """Call ``boot_genomes`` exactly once per process, ever."""
    global _booted
    with _lock:
        if _booted:
            return
        _booted = True
    try:
        from . import loader
        loader.boot_genomes()
    except Exception:
        # Never let a genome boot failure take down the first request.
        logger.exception('[Neuroplasticity] boot_genomes failed')


def run_now() -> None:
    """Synchronous entry point for callers that need genomes loaded now.

    Intended for diagnostic shells and tests. Idempotent — second call
    in the same process is a no-op.
    """
    _run_once()
