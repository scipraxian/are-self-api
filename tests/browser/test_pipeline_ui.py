from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import sync_playwright
from pipelines.models import BuildProfile, PipelineRun, PipelineStepRun
from django.utils import timezone
import asyncio
import os

# Set Windows Policy for Playwright
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

class PipelineUITest(StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        self.profile = BuildProfile.objects.create(name="UI Test Profile", headless=True)
        # Create a run that will be used for testing
        self.run = PipelineRun.objects.create(profile=self.profile, status='RUNNING')
        self.step = PipelineStepRun.objects.create(
            pipeline_run=self.run,
            step_name="Test Step",
            status='SUCCESS',
            started_at=timezone.now(),
            finished_at=timezone.now(),
            logs="First Line\nSecond Line\nEnd of Logs"
        )
        self.browser = None
        self.playwright = None

    def tearDown(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        super().tearDown()

    def test_monitor_interaction(self):
        """Verify that clicking a step row exposes the log container."""
        # This is a duplicate of test_pipeline_step_click_shows_logs but matches the specific task requirement
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        page = self.browser.new_page()
        monitor_url = f"{self.live_server_url}/pipelines/monitor/{self.run.id}/"
        page.goto(monitor_url)
        
        # Click the row
        page.locator("tr.step-row").first.click()
        
        # Wait for the log container to be visible
        # We check for the class as requested by the task 'exposes the #log-container element'
        # but since IDs must be unique per step, we use the class or a pattern.
        log_container = page.locator(".log-container").first
        log_container.wait_for(state="visible", timeout=2000)
        self.assertTrue(log_container.is_visible(), "Log container was not exposed after click")

    def test_pipeline_step_click_shows_logs(self):
        self.playwright = sync_playwright().start()
        # Launch browser in headless mode but can switch to headless=False for debugging
        self.browser = self.playwright.chromium.launch(headless=True)
        page = self.browser.new_page()

        # 1. Navigate to the monitor page directly
        monitor_url = f"{self.live_server_url}/pipelines/monitor/{self.run.id}/"
        page.goto(monitor_url)
        
        # 2. Verify Step Row alignment
        step_cell = page.get_by_text("Test Step")
        self.assertTrue(step_cell.is_visible(), "Step name not visible in table")
        
        # 3. Click the row to toggle logs
        row = page.locator("tr.step-row").first
        row.click()
        
        # 4. Verify Log Container visibility
        log_container = page.locator(f"#logs-{self.step.id}")
        log_container.wait_for(state="visible", timeout=2000)
        self.assertTrue(log_container.is_visible(), "Log container did not become visible after click")
        
        # 5. Verify Content of Logs (HTMX loads this separately)
        page.wait_for_selector(f"#logs-{self.step.id} pre", timeout=5000)
        
        log_content = page.locator(f"#logs-{self.step.id} pre").inner_text()
        self.assertIn("First Line", log_content)
        self.assertIn("End of Logs", log_content)

        print(f"Verified logs for step {self.step.id}: {log_content[:20]}...")
