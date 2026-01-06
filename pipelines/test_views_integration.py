from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from pipelines.models import BuildProfile, PipelineRun, PipelineStepRun

class PipelineViewIntegrationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.profile = BuildProfile.objects.create(name="Integration Test Profile")
        
    def test_monitor_view_renders_correctly_when_running(self):
        """
        CRITICAL TEST: Verifies that live_monitor.html renders without 
        TemplateSyntaxError when the pipeline is in the RUNNING state.
        This catches the 'run.status==RUNNING' bug.
        """
        # 1. Create a RUNNING pipeline (This triggers the specific if-blocks in the template)
        run = PipelineRun.objects.create(
            profile=self.profile, 
            status='RUNNING',
            created_at=timezone.now()
        )
        
        # 2. Create a step so the table isn't empty
        PipelineStepRun.objects.create(
            pipeline_run=run,
            step_name="Test Step",
            status='RUNNING',
            started_at=timezone.now()
        )

        # 3. Request the Monitor View
        url = reverse('pipeline_live_monitor', args=[run.id])
        response = self.client.get(url)

        # 4. Assertions
        # If the template has syntax errors (like missing spaces), this returns 500
        self.assertEqual(response.status_code, 200, "Monitor view crashed! Likely a TemplateSyntaxError.")
        
        # Verify the specific buttons rendered (Stop button only appears when running)
        self.assertContains(response, "STOP", msg_prefix="Stop button missing (Template logic fail)")
        self.assertNotContains(response, "DONE", msg_prefix="Done button appeared when it should be hidden")

    def test_monitor_view_renders_correctly_when_success(self):
        """Verifies the DONE state rendering."""
        run = PipelineRun.objects.create(
            profile=self.profile, 
            status='SUCCESS'
        )
        
        url = reverse('pipeline_live_monitor', args=[run.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DONE")
        self.assertNotContains(response, "STOP")