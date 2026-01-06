from django.test import TestCase
from unittest import mock
from pipelines.models import BuildProfile, PipelineRun, PipelineStepRun
from pipelines.tasks import run_headless_tests_task, run_staging_build_task, orchestrate_pipeline
from environments.models import ProjectEnvironment
import os

class BuildProfileTest(TestCase):
    def setUp(self):
        self.env = ProjectEnvironment.objects.create(
            name="Test Env",
            project_root="C:/Project",
            engine_root="C:/UE5",
            is_active=True
        )

    def test_create_build_profile(self):
        """Test that we can create a build profile and retrieve its values."""
        profile = BuildProfile.objects.create(
            name="Nightly",
            headless=True,
            staging=True,
            steam=False
        )
        saved_profile = BuildProfile.objects.get(name="Nightly")
        self.assertEqual(saved_profile.headless, True)

    @mock.patch('pipelines.tasks.subprocess.Popen')
    def test_headless_validator_task(self, mock_popen):
        """Test that the headless validator generates the correct UE5 command."""
        # Setup Mock Process
        process_mock = mock.Mock()
        process_mock.stdout.readline.side_effect = ["Initializing...\n", ""]
        process_mock.stdout.__enter__ = mock.Mock(return_value=process_mock.stdout)
        process_mock.stdout.__exit__ = mock.Mock(return_value=None)
        process_mock.poll.side_effect = [None, 0]
        process_mock.returncode = 0
        mock_popen.return_value = process_mock
        
        # Run (with os.path.exists mocked to avoid disk reads)
        with mock.patch('os.path.exists', return_value=False):
            run_headless_tests_task()
        
        # Verify Args
        args, kwargs = mock_popen.call_args
        cmd = args[0]
        self.assertIn("-nosplash", cmd)
        self.assertIn("-stdout", cmd)

    @mock.patch('pipelines.tasks.subprocess.Popen')
    def test_headless_task_with_tracking(self, mock_popen):
        """Test that the headless task creates step records and streams logs."""
        profile = BuildProfile.objects.create(name="Tracked", headless=True)
        run = PipelineRun.objects.create(profile=profile)
        
        # Setup Mock Process
        process_mock = mock.Mock()
        process_mock.stdout.readline.side_effect = ["Log Line 1\n", ""]
        process_mock.stdout.__enter__ = mock.Mock(return_value=process_mock.stdout)
        process_mock.stdout.__exit__ = mock.Mock(return_value=None)
        process_mock.poll.side_effect = [None, 0]
        process_mock.returncode = 0
        mock_popen.return_value = process_mock
        
        with mock.patch('os.path.exists', return_value=False):
            run_headless_tests_task(run.id)
        
        self.assertEqual(run.steps.count(), 1)
        step = run.steps.first()
        self.assertIn("Log Line 1", step.logs)

    @mock.patch('pipelines.tasks.subprocess.Popen')
    def test_staging_build_task(self, mock_popen):
        """Test that the staging builder generates the correct UAT command."""
        process_mock = mock.Mock()
        process_mock.stdout.readline.side_effect = ["Building...\n", ""]
        process_mock.stdout.__enter__ = mock.Mock(return_value=process_mock.stdout)
        process_mock.stdout.__exit__ = mock.Mock(return_value=None)
        process_mock.poll.side_effect = [None, 0]
        process_mock.returncode = 0
        mock_popen.return_value = process_mock
        
        with mock.patch('os.path.exists', return_value=False):
            run_staging_build_task()
        
        args, kwargs = mock_popen.call_args
        cmd = args[0]
        self.assertIn("BuildCookRun", cmd)

    def test_orchestrator_chain_generation(self):
        """Test that the orchestrator creates the correct Celery chain based on profile."""
        profile = BuildProfile.objects.create(name="Full Pipeline", headless=True, staging=True)
        run = PipelineRun.objects.create(profile=profile)
        
        chain_res = orchestrate_pipeline(profile.id, run.id)
        self.assertEqual(len(chain_res.tasks), 3)