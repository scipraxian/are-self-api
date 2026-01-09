import os
import sys
import asyncio
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import sync_playwright, expect
from hydra.models import (
    HydraHead, HydraSpell, HydraExecutable, HydraSpellbook, 
    HydraSpawn, HydraHeadStatus, HydraSpawnStatus
)
from environments.models import ProjectEnvironment

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

class LiveMonitorTests(StaticLiveServerTestCase):
    def setUp(self):
        self.env = ProjectEnvironment.objects.create(name="BrowserEnv", is_active=True)
        # Create full range of statuses to avoid IntegrityErrors during nudge/poll
        for i, name in [(1, "Created"), (2, "Pending"), (3, "Running"), (4, "Success"), (5, "Failed")]:
            HydraHeadStatus.objects.create(id=i, name=name)
            HydraSpawnStatus.objects.create(id=i, name=name)
            
        exe = HydraExecutable.objects.create(name="Tool", slug="tool")
        spell = HydraSpell.objects.create(name="Spell", executable=exe)
        book = HydraSpellbook.objects.create(name="Book")
        self.spawn = HydraSpawn.objects.create(spellbook=book, status_id=1)
        self.head = HydraHead.objects.create(
            spawn=self.spawn, 
            spell=spell, 
            status_id=1,
            spell_log="Initial Log Content..."
        )

    def test_log_interaction_stability(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # 1. Load Monitor
            url = f"{self.live_server_url}/hydra/monitor/{self.spawn.id}/"
            page.goto(url)
            
            # 2. Click Row to Reveal Logs
            row_id = str(self.head.id)
            page.click(f"#row-{row_id}")
            
            # 3. Manually Trigger HTMX Load
            page.evaluate(f"htmx.trigger('#log-wrapper-{row_id}', 'load_now')")
            
            # 4. Expect Content in the PAYLOAD div (Inner Target)
            log_box = page.locator(f"#log-payload-{row_id}")
            expect(log_box).to_contain_text("Initial Log Content...", timeout=5000)
            
            # 5. Verify Structure Stability
            # Ensure the wrapper still exists (proving it wasn't overwritten)
            wrapper = page.locator(f"#log-wrapper-{row_id}")
            expect(wrapper).to_be_visible()
            
            browser.close()