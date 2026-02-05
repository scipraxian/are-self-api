import os
import time
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import sync_playwright, expect
from talos_agent.models import TalosAgentRegistry, TalosAgentStatus

import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Ensure we use a clean environment for testing
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"


class DashboardBrowserTests(StaticLiveServerTestCase):

    def setUp(self):
        # Setup data
        from hydra.models import HydraSpellbook
        HydraSpellbook.objects.create(name="Fast Validate")
        status_online = TalosAgentStatus.objects.get_or_create(
            id=2, defaults={'name': 'ONLINE'})[0]
        TalosAgentRegistry.objects.create(hostname="TestAgent01",
                                          ip_address="127.0.0.1",
                                          status=status_online)

    def test_dashboard_interaction(self):
        with sync_playwright() as p:
            # Launch browser (headless for CI/Speed)
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # 1. Load Dashboard Index
            print(f"Loading {self.live_server_url}")
            page.goto(self.live_server_url)

            # Verify Header
            expect(page.locator('.sys-title')).to_contain_text("TALOS ORCHESTRATOR")

            # 2. Verify Protocol List is visible
            expect(page.locator('.launch-pad')).to_be_visible()
            expect(page.locator('.launch-btn')).to_have_count(1)
            expect(page.locator('.launch-btn')).to_contain_text("Fast Validate")

            # 3. Sidebar toggle
            page.click('.hamburger')
            expect(page.locator('#system-menu')).to_be_visible()
            expect(page.locator('.menu-item').first).to_contain_text("Sonar Registry")

            browser.close()
