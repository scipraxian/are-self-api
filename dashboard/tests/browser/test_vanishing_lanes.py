import asyncio
import os
import sys
import time

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import expect, sync_playwright

from environments.models import TalosExecutable
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


class DashboardPersistenceTests(StaticLiveServerTestCase):
    """
    Browser tests to verify UI elements do not vanish during HTMX polling.
    """

    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',  # <--- REQUIRED for Hydra FK
        'hydra/fixtures/initial_data.json',
    ]

    def setUp(self):
        self.status_running = HydraSpawnStatus.objects.get(id=3)
        self.status_success = HydraSpawnStatus.objects.get(id=4)

        self.book = HydraSpellbook.objects.create(name='Persistence Protocol')
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, status=self.status_running
        )

        exe = TalosExecutable.objects.first()
        spell = HydraSpell.objects.create(
            name='Test Spell', talos_executable=exe
        )

        HydraHead.objects.create(
            spawn=self.spawn,
            spell=spell,
            status_id=1,  # Created
        )

    def test_swimlane_persistence(self):
        """
        Loads the dashboard and asserts the swimlane REMAINS in the DOM
        after multiple HTMX polling cycles.
        """
        _force_windows_asyncio_subprocess_support()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto(f'{self.live_server_url}/')

            lane_id = f'#lane-wrapper-{self.spawn.id}'
            lane = page.locator(lane_id)

            print(f'Watching Lane: {lane_id}')
            expect(lane).to_be_visible(timeout=5000)

            print('  > Waiting for polling cycles...')
            for i in range(6):
                time.sleep(1)
                count = lane.count()
                if count == 0:
                    print('  !!! FATAL: Lane vanished!')
                    print(page.content())
                self.assertEqual(count, 1, f'Lane vanished at second {i + 1}!')

            print('  > Updating DB status...')
            self.spawn.status = self.status_success
            self.spawn.save()

            time.sleep(3)

            expect(lane).to_contain_text('Success')
            expect(lane).to_be_visible()

            browser.close()
