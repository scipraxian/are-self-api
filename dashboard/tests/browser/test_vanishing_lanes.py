import asyncio
import os
import sys
import time

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import expect, sync_playwright

from environments.models import ProjectEnvironment, TalosExecutable
from hydra.models import (
    HydraHead,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellbook,
)

# Ensure async safety for Django ORM
os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'


def _force_windows_asyncio_subprocess_support() -> None:
    """
    Playwright launches a driver via asyncio subprocesses.
    On Windows, SelectorEventLoopPolicy does NOT support subprocesses and raises NotImplementedError.

    Some test runners/plugins can set WindowsSelectorEventLoopPolicy globally.
    This function forces the Proactor policy and also resets the current loop to one created
    under the correct policy.
    """
    if sys.platform != 'win32':
        return

    # 1) Force Proactor policy (subprocess-capable on Windows)
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # 2) Ensure the current thread has a loop created under that policy
    #    (important if something already set a loop earlier)
    try:
        old_loop = asyncio.get_event_loop()
        old_loop.close()
    except Exception:
        pass

    asyncio.set_event_loop(asyncio.new_event_loop())
