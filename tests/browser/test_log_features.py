# TODO: rebuild to new defiitions
# import asyncio
# import os
# import sys
# import time
#
# import pytest
# from django.contrib.staticfiles.testing import StaticLiveServerTestCase
# from playwright.sync_api import expect, sync_playwright
#
# from hydra.models import (HydraHead, HydraHeadStatus, HydraSpawn, HydraSpawnStatus,
#                           HydraSpell, HydraSpellbook)
#
# if sys.platform == 'win32':
#     asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
#
# os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
#
# @pytest.mark.skip(reason='Occasional Fail')  # this test fails occasionally.
# class LogFeaturesTests(StaticLiveServerTestCase):
#     def setUp(self):
#         # Clean up existing data to ensure fresh IDs if needed,
#         # but StaticLiveServerTestCase handles this usually.
#
#         self.env = ProjectEnvironment.objects.create(name="ProjectX", is_active=True)
#         self.hydra_env = HydraEnvironment.objects.create(project_environment=self.env, name="TestEnv")
#         self.book = HydraSpellbook.objects.create(name="LogTest")
#
#         for i, name in [(1, "Created"), (2, "Pending"), (3, "Running"), (4, "Success"), (5, "Failed")]:
#             HydraSpawnStatus.objects.get_or_create(id=i, name=name)
#             HydraHeadStatus.objects.get_or_create(id=i, name=name)
#
#         self.exe = HydraExecutable.objects.create(name="TestExe", slug="test-exe")
#         self.spell = HydraSpell.objects.create(name="TestSpell", executable=self.exe)
#         self.spawn = HydraSpawn.objects.create(
#             spellbook=self.book,
#             environment=self.hydra_env,
#             status_id=HydraSpawnStatus.RUNNING
#         )
#         self.head = HydraHead.objects.create(
#             spawn=self.spawn,
#             spell=self.spell,
#             status_id=HydraHeadStatus.RUNNING,
#             spell_log="Line 1\nLine 2\n"
#         )
#
#     def test_log_buttons_and_scroll(self):
#         with sync_playwright() as p:
#             browser = p.chromium.launch(headless=True)
#             page = browser.new_page()
#
#             # 1. Open Monitor Page
#             url = f"{self.live_server_url}/hydra/monitor/{self.spawn.id}/"
#             print(f"DEBUG: Visiting {url}")
#             page.goto(url)
#
#             # 2. Click Row to Expand Logs
#             # We use wait_for_selector to be sure it's rendered
#             page.wait_for_selector(f"#row-{self.head.id}")
#             page.click(f"#row-{self.head.id}")
#
#             # 3. Verify Buttons are visible (proving head_log.html loaded)
#             print("DEBUG: Checking for buttons...")
#             expect(page.get_by_role("button", name="Copy")).to_be_visible(timeout=10000)
#             expect(page.get_by_role("button", name="Download")).to_be_visible(timeout=10000)
#
#             # 4. Verify Tabs work
#             print("DEBUG: Testing tabs...")
#             page.click("text=System Context")
#             expect(page.get_by_text("No system events logged.")).to_be_visible(timeout=10000)
#
#             # 5. Verify Scroll behavior
#             print("DEBUG: Testing scroll...")
#             page.click("text=Output Stream")
#
#             # Fill the log to exceed max-height (400px)
#             long_log = "\n".join([f"Log Line {i:03d}" for i in range(100)])
#             self.head.spell_log = long_log
#             self.head.save()
#
#             # Give HTMX time to poll (2s) and swap
#             time.sleep(3)
#
#             container_id = f"#log-scroll-container-{self.head.id}"
#
#             # Check if scrolled to bottom
#             # container.scrollHeight - container.scrollTop - container.clientHeight < threshold
#             metrics = page.evaluate(f"""
#                 () => {{
#                     const el = document.querySelector('{container_id}');
#                     if (!el) return null;
#                     return {{
#                         scrollHeight: el.scrollHeight,
#                         scrollTop: el.scrollTop,
#                         clientHeight: el.clientHeight,
#                         diff: el.scrollHeight - el.scrollTop - el.clientHeight
#                     }};
#                 }}
#             """)
#             print(f"DEBUG: Scroll metrics: {metrics}")
#             self.assertIsNotNone(metrics)
#             self.assertLess(metrics['diff'], 60, "Log container should be scrolled to bottom")
#
#             browser.close()
