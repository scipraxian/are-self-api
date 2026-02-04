import os
import sys
import asyncio
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import sync_playwright, expect
from talos_agent.models import TalosAgentRegistry
from environments.models import TalosExecutable
from hydra.models import HydraSpellbook, HydraSpawn, HydraSpawnStatus, HydraHeadStatus, HydraSpell, HydraHead

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"


class HydraHistoryTests(StaticLiveServerTestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
        'talos_frontal/fixtures/initial_data.json',
        'talos_reasoning/fixtures/initial_data.json'
    ]

    def setUp(self):
        self.book = HydraSpellbook.objects.create(name="Fast Validate")

        # We need these for the view to work
        for i, name in [(1, "Created"), (2, "Pending"), (3, "Running"),
                        (4, "Success"), (5, "Failed")]:
            HydraSpawnStatus.objects.get_or_create(id=i, name=name)
            HydraHeadStatus.objects.get_or_create(id=i, name=name)

    def test_history_visibility_and_navigation(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # 1. Initial State - No History
            page.goto(self.live_server_url)
            expect(page.get_by_text(
                "No mission history available.")).to_be_visible()

            # 2. Create a finished run
            exe = TalosExecutable.objects.create(name="TestExe",
                                                 executable="test.exe")
            spell = HydraSpell.objects.create(name="TestSpell",
                                              talos_executable=exe)
            spawn = HydraSpawn.objects.create(
                spellbook=self.book, status_id=HydraSpawnStatus.SUCCESS)
            HydraHead.objects.create(spawn=spawn,
                                     spell=spell,
                                     status_id=HydraHeadStatus.SUCCESS)

            page.reload()

            # 3. Verify history item appears
            expect(page.get_by_text("Recent Missions")).to_be_visible()
            expect(page.locator(".history-item")).to_have_count(1)
            expect(page.locator(".history-item").first).to_contain_text(
                "Fast Validate")
            expect(
                page.locator(".history-item").first).to_contain_text("Success")

            # 4. Create another run (Active this time)
            spawn2 = HydraSpawn.objects.create(
                spellbook=self.book, status_id=HydraSpawnStatus.RUNNING)
            HydraHead.objects.create(spawn=spawn2,
                                     spell=spell,
                                     status_id=HydraHeadStatus.RUNNING)

            page.reload()

            # 5. Verify both appear (ordered by -created)
            expect(page.locator(".history-item")).to_have_count(2)
            # The active one should be at the top of history too
            expect(
                page.locator(".history-item").first).to_contain_text("Running")
            expect(
                page.locator(".history-item").nth(1)).to_contain_text("Success")

            # 6. Click history item to navigate
            page.locator(".history-item").nth(1).click()

            # 7. Verify we are on the monitor page (full page)
            expect(page).to_have_url(
                f"{self.live_server_url}/hydra/monitor/{spawn.id}/?full=True")
            expect(page.get_by_text(
                f"OPERATION: {self.book.name}")).to_be_visible()
            expect(page.locator(".status-text.status-success")).to_be_visible()

            browser.close()

    def test_history_limit_to_five(self):
        # Create 6 runs
        for i in range(6):
            HydraSpawn.objects.create(spellbook=self.book,
                                      status_id=HydraSpawnStatus.SUCCESS)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(self.live_server_url)

            # Should only show 5
            expect(page.locator(".history-item")).to_have_count(5)

            browser.close()
