import asyncio
import os
import sys

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import expect, sync_playwright

from environments.models import ProjectEnvironment
from hydra.models import (
    HydraEnvironment,
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellbook,
)

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'


class LogClippingTests(StaticLiveServerTestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json',
    ]

    def setUp(self):
        self.env = ProjectEnvironment.objects.create(
            name='ClippingEnv', is_active=True
        )
        self.hydra_env = HydraEnvironment.objects.create(
            project_environment=self.env, name='TestEnv'
        )

        for i, name in [
            (1, 'Created'),
            (2, 'Pending'),
            (3, 'Running'),
            (4, 'Success'),
            (5, 'Failed'),
        ]:
            HydraHeadStatus.objects.get_or_create(id=i, name=name)
            HydraSpawnStatus.objects.get_or_create(id=i, name=name)

        spell = HydraSpell.objects.create(name='Spell', talos_executable_id=1)
        book = HydraSpellbook.objects.create(name='Book')
        self.spawn = HydraSpawn.objects.create(
            spellbook=book,
            environment=self.hydra_env,
            status_id=HydraSpawnStatus.RUNNING,
        )
        self.head = HydraHead.objects.create(
            spawn=self.spawn,
            spell=spell,
            status_id=HydraHeadStatus.RUNNING,
            spell_log='Sample log content for clipping test...',
        )

    def test_log_buttons_visibility(self):
        """Verify that log buttons are visible and not clipped at narrow widths."""
        with sync_playwright() as p:
            # Narrow viewport to force potential clipping
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': 400, 'height': 800}
            )
            page = context.new_page()

            # Load the monitor (which contains the log)
            page.goto(f'{self.live_server_url}/hydra/monitor/{self.spawn.id}/')

            # Expand logs
            page.click(f'#row-{self.head.id}')

            # Wait for logs to load via HTMX
            page.wait_for_selector('.log-interface', state='visible')

            # Get bounding boxes
            container = page.locator('.container')
            container_box = container.bounding_box()
            download_btn = page.locator("button:has-text('Download')")
            btn_box = download_btn.bounding_box()

            # Assertions
            # 1. Button should be visible
            expect(download_btn).to_be_visible()

            # 2. Button right edge should be within viewport width (400)
            self.assertLessEqual(
                btn_box['x'] + btn_box['width'],
                400,
                f'Download button is clipped by viewport (x={btn_box["x"]}, w={btn_box["width"]})',
            )

            # 3. Button should be within the main container's horizontal bounds
            # Adding a small epsilon for sub-pixel rendering if necessary, but 1px should be fine
            self.assertLessEqual(
                btn_box['x'] + btn_box['width'],
                container_box['x'] + container_box['width'] + 1,
                'Download button overflows container',
            )

            browser.close()
