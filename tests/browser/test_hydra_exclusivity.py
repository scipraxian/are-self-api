import os
import sys
import asyncio
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import sync_playwright, expect
from core.models import RemoteTarget
from environments.models import ProjectEnvironment
from hydra.models import HydraSpellbook, HydraSpawn, HydraSpawnStatus, HydraHeadStatus, HydraEnvironment

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

class HydraExclusivityTests(StaticLiveServerTestCase):
    def setUp(self):
        self.env = ProjectEnvironment.objects.create(name="ProjectX", is_active=True)
        self.hydra_env = HydraEnvironment.objects.create(project_environment=self.env, name="TestEnv")
        self.book1 = HydraSpellbook.objects.create(name="Fast Validate")
        self.book2 = HydraSpellbook.objects.create(name="Full Run")
        
        # We need these for the view to work
        for i, name in [(1, "Created"), (2, "Pending"), (3, "Running"), (4, "Success"), (5, "Failed")]:
            HydraSpawnStatus.objects.get_or_create(id=i, name=name)
            HydraHeadStatus.objects.get_or_create(id=i, name=name)

    def test_buttons_hidden_during_run(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # 1. Initial State - Both buttons visible
            page.goto(self.live_server_url)
            page.wait_for_selector(".hydra-btn", state="visible")
            
            expect(page.get_by_role("button", name="Fast Validate")).to_be_visible()
            expect(page.get_by_role("button", name="Full Run")).to_be_visible()
            
            # 2. Simulate an active run with a head so it doesn't get cleaned up immediately
            from hydra.models import HydraSpell, HydraExecutable, HydraHead
            exe = HydraExecutable.objects.create(name="TestExe", slug="test-exe")
            spell = HydraSpell.objects.create(name="TestSpell", executable=exe)
            spawn = HydraSpawn.objects.create(
                spellbook=self.book1,
                environment=self.hydra_env,
                status_id=HydraSpawnStatus.RUNNING
            )
            HydraHead.objects.create(spawn=spawn, spell=spell, status_id=HydraHeadStatus.RUNNING)

            page.reload()

            # 3. Verify exclusivity - "Run" buttons should be gone, Monitor should be there
            expect(page.get_by_role("button", name="Fast Validate")).not_to_be_visible()
            expect(page.get_by_role("button", name="Full Run")).not_to_be_visible()
            expect(page.get_by_text("OPERATION: Fast Validate")).to_be_visible()
            expect(page.locator(".monitor-table")).to_be_visible()
            
            # 4. Finish the head
            head = spawn.heads.first()
            head.status_id = HydraHeadStatus.SUCCESS
            head.save()

            # Wait for HTMX poll to update the UI and show DISMISS button
            # We don't reload here because we want to test the dynamic swap/poll behavior
            expect(page.get_by_text("DISMISS")).to_be_visible(timeout=10000)
            page.click("text=DISMISS")
            
            # 5. Buttons should return
            expect(page.get_by_role("button", name="Fast Validate")).to_be_visible()
            expect(page.get_by_role("button", name="Full Run")).to_be_visible()
            expect(page.get_by_text("OPERATION: Fast Validate")).not_to_be_visible()

            browser.close()

    def test_zombie_spawn_cleanup(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # 1. Create a zombie spawn (Running but no heads)
            HydraSpawn.objects.create(
                spellbook=self.book1,
                environment=self.hydra_env,
                status_id=HydraSpawnStatus.RUNNING
            )
            
            # 2. Visit home
            page.goto(self.live_server_url)
            
            # 3. The nudge in DashboardHomeView should have fixed it immediately
            expect(page.get_by_role("button", name="Fast Validate")).to_be_visible()
            expect(page.get_by_role("button", name="Full Run")).to_be_visible()
            expect(page.get_by_text("RUNNING")).not_to_be_visible()
            
            # Verify DB state
            spawn = HydraSpawn.objects.first()
            self.assertEqual(spawn.status_id, HydraSpawnStatus.SUCCESS)
            
            browser.close()
