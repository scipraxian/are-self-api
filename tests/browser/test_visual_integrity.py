import os
import sys
import asyncio
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import sync_playwright, expect
from core.models import RemoteTarget
from environments.models import ProjectEnvironment
from talos_agent.version import VERSION as SERVER_VERSION

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

class VisualIntegrityTests(StaticLiveServerTestCase):
    def setUp(self):
        ProjectEnvironment.objects.create(name="ProjectX", is_active=True)
        self.agent = RemoteTarget.objects.create(
            hostname="ColorTestAgent",
            ip_address="127.0.0.1",
            status="ONLINE",
            version="1.0.0"
        )

    def test_button_vibrancy(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # 1. HOME PAGE - BIG RED BUTTON
            page.goto(self.live_server_url)
            page.wait_for_selector(".big-red-button", state="visible")
            
            build_btn = page.locator(".big-red-button")
            # Gradient is complex. Check both background and backgroundImage
            bg_computed = build_btn.evaluate("el => { const s = window.getComputedStyle(el); return { image: s.backgroundImage, color: s.backgroundColor, bg: s.background }; }")
            print(f"DEBUG: Big Red Button Style: {bg_computed}")
            
            is_red = "rgb(239, 68, 68)" in bg_computed['image'] or "rgb(239, 68, 68)" in bg_computed['bg']
            self.assertTrue(is_red, f"Big Red Button is NOT the correct shade of red! Styles: {bg_computed}")

            # 2. DETAIL PAGE - CONTROL BUTTONS
            page.goto(f"{self.live_server_url}/agent-detail/{self.agent.pk}/")
            page.wait_for_selector(".btn-launch", state="visible")
            
            # LAUNCH -> GREEN (#22c55e -> 34, 197, 94)
            launch_color = page.locator(".btn-launch").evaluate("el => window.getComputedStyle(el).backgroundColor")
            print(f"DEBUG: Launch Button Color: {launch_color}")
            self.assertIn("rgb(34, 197, 94)", launch_color, "Launch button is NOT green!")

            # KILL -> RED (#ef4444 -> 239, 68, 68)
            kill_color = page.locator(".btn-kill").evaluate("el => window.getComputedStyle(el).backgroundColor")
            print(f"DEBUG: Kill Button Color: {kill_color}")
            self.assertIn("rgb(239, 68, 68)", kill_color, "Kill button is NOT red!")

            # UPDATE -> BLUE (#3b82f6 -> 59, 130, 246)
            update_color = page.locator(".btn-update").evaluate("el => window.getComputedStyle(el).backgroundColor")
            print(f"DEBUG: Update Button Color: {update_color}")
            self.assertIn("rgb(59, 130, 246)", update_color, "Update button is NOT blue!")

            browser.close()

if __name__ == '__main__':
    pass
