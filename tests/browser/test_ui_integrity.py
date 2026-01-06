import os
import sys
import asyncio
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import sync_playwright, expect
from core.models import RemoteTarget
from environments.models import ProjectEnvironment
from talos_agent.bin.agent_service import VERSION as SERVER_VERSION

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

class UIIntegrityTests(StaticLiveServerTestCase):
    def setUp(self):
        # Create a project env
        ProjectEnvironment.objects.create(name="Talos Project", is_active=True)
        # Create a "Legacy" agent (needs update)
        RemoteTarget.objects.create(
            hostname="MismatchedAgent",
            ip_address="192.168.1.10",
            version="1.0.0", # Server is 2.1.2
            status="ONLINE"
        )
        # Create a "Synced" agent
        RemoteTarget.objects.create(
            hostname="SyncedAgent",
            ip_address="192.168.1.11",
            version=SERVER_VERSION,
            status="ONLINE"
        )

    def test_rendering_and_mismatch_badges(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Use a longer timeout for HTMX transitions
            page.set_default_timeout(10000)
            
            # 1. Check Home Page
            page.goto(self.live_server_url)
            
            # Wait for content to stabilize
            page.wait_for_selector(".agent-grid", state="visible")
            
            body_text = page.inner_text("body")
            try:
                self.assertNotIn("{{", body_text, f"Found raw template tags on home page! Content: {body_text[:500]}")
                self.assertNotIn("}}", body_text, "Found raw template tags on home page!")
                
                # Verify cards exist
                expect(page.locator('.agent-card')).to_have_count(2)
                
                # Verify the pulsing dot appears for the mismatched agent
                mismatched_card = page.locator('.agent-card', has_text="MismatchedAgent")
                expect(mismatched_card).to_be_visible()
                
                # The pulse indicator is a span with a title
                expect(mismatched_card.locator('span[title*="Update Available"]')).to_be_visible()
            except AssertionError as e:
                print(f"FAILED UI TEST. Page Content:\n{page.content()}")
                raise e

            # 2. Check Detail Page
            page.locator('.agent-card', has_text="MismatchedAgent").click()
            page.wait_for_selector(".agent-detail-container", state="visible")
            
            detail_text = page.inner_text(".agent-detail-container")
            self.assertNotIn("{{", detail_text, "Found raw template tags on detail page!")
            expect(page.locator('.update-badge')).to_be_visible()

            browser.close()

if __name__ == '__main__':
    from django.core.management import execute_from_command_line
    # This is a bit tricky to run standalone without manage.py test
    # but the tool call will run it via manage.py test.
    pass
