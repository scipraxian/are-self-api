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
            expect(page.locator('h1')).to_contain_text("Talos Command Center")

            # 2. Verify Agent List is visible and has our agent
            expect(page.locator('.agent-grid')).to_be_visible()
            expect(page.locator('.agent-card')).to_have_count(1)
            expect(page.locator('.agent-card .hostname')).to_contain_text(
                "TestAgent01")

            # 3. VERIFY STYLING (The Hydra Button must be Violet)
            # This ensures the CSS injected via partials is actually working.
            build_btn = page.locator('.hydra-btn')
            expect(build_btn).to_be_visible()

            # The style uses a linear-gradient starting with #8b5cf6 (rgb 139, 92, 246)
            bg_style = build_btn.evaluate(
                "el => window.getComputedStyle(el).backgroundImage")
            if "rgb(139, 92, 246)" not in bg_style and "linear-gradient" not in bg_style:
                raise AssertionError(
                    f"Button is not Violet! Computed background: {bg_style}")

            # 4. Agent Detail and Update Button
            # Navigate to agent detail
            page.click('.agent-card-link')

            # Verify we are on detail page
            expect(page.locator('h1')).to_contain_text("TestAgent01")

            # Verify "Push Update" button exists
            update_btn = page.locator('.btn-update')
            expect(update_btn).to_be_visible()
            expect(update_btn).to_contain_text("Push Update")

            browser.close()
