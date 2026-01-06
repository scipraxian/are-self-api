import os
import sys
import asyncio
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import sync_playwright, expect
from core.models import RemoteTarget
from environments.models import ProjectEnvironment
from pipelines.models import BuildProfile, PipelineRun

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

class FastValidateFlowTests(StaticLiveServerTestCase):
    def setUp(self):
        self.env = ProjectEnvironment.objects.create(name="HSHVacancy", is_active=True, project_root="C:/talos")
        self.profile = BuildProfile.objects.create(name="Fast Validate", headless=True)
        self.agent = RemoteTarget.objects.create(
            hostname="TestAgent",
            ip_address="127.0.0.1",
            status="ONLINE",
            version="2.1.3"
        )

    def test_fast_validate_ui_flow(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # 1. Visit Home
            page.goto(self.live_server_url)
            
            # 2. Check if Fast Validate button exists and is red
            page.wait_for_selector(".big-red-button", state="visible")
            btn = page.locator(".big-red-button")
            self.assertIn("🚀 FAST VALIDATE", btn.inner_text().upper())
            
            # Verify it's red
            bg_computed = btn.evaluate("el => window.getComputedStyle(el).backgroundImage")
            self.assertIn("rgb(239, 68, 68)", bg_computed, "Big Red Button should HAVE red gradient")

            # 3. Click Fast Validate
            btn.click()
            
            # 4. Wait for redirect div (it's fast, so we might miss it, but let's see if monitor appears)
            # The monitor has h3 "Campaign Monitor"
            page.wait_for_selector("h3:has-text('Campaign Monitor')", state="visible", timeout=5000)
            
            # 5. Check if it swapped correctly (root element should still have id campaign-launcher)
            launcher = page.locator("#campaign-launcher")
            expect(launcher).to_be_visible()
            
            # 6. Check if status row for the step exists
            page.wait_for_selector(".step-row", state="visible")
            
            # 7. Mock finishing the run to test the "Done" button
            run = PipelineRun.objects.first()
            run.status = 'SUCCESS'
            run.save()
            
            # 8. Trigger a refresh to show the "Done" button
            # We can either wait for polling (if we had it on the whole page) or just reload
            page.reload()
            
            # 9. Verify "Done" button exists
            page.wait_for_selector(".reset-button:has-text('Done')", state="visible")
            done_btn = page.locator(".reset-button:has-text('Done')")
            
            # 10. Click "Done" and verify we back to the start
            done_btn.click()
            page.wait_for_selector(".big-red-button", state="visible")
            
            browser.close()
