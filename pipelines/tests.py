from django.test import TestCase
from unittest import mock
from pipelines.models import BuildProfile, PipelineRun
from pipelines.tasks import run_headless_tests_task, run_staging_build_task, orchestrate_pipeline
from environments.models import ProjectEnvironment

class BuildProfileTest(TestCase):
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
        self.assertEqual(saved_profile.staging, True)
        self.assertEqual(saved_profile.steam, False)

    @mock.patch('subprocess.run')
    def test_headless_validator_task(self, mock_run):
        """Test that the headless validator generates the correct UE5 command."""
        # Setup environment
        env = ProjectEnvironment.objects.create(
            name="Test Env",
            project_root="C:/Project",
            engine_root="C:/UE5",
            is_active=True
        )
        
        # Mock successful run
        mock_run.return_value = mock.Mock(returncode=0)
        
        # Run task
        run_headless_tests_task()
        
        # Assert subprocess.run was called with correct arguments
        # We expect EditorCmd, project path, and the headless flags
        args, kwargs = mock_run.call_args_list[1] # [0] is compilation, [1] is test run
        cmd = args[0]
        
        self.assertIn("-nullrhi", cmd)
        self.assertIn("-unattended", cmd)
        self.assertIn("-nopause", cmd)
        self.assertIn("Automation RunTests", cmd[len(cmd)-2]) # It's in the ExecCmds arg

    @mock.patch('subprocess.run')
    def test_headless_task_with_tracking(self, mock_run):
        """Test that the headless task creates step records when a run_id is provided."""
        env = ProjectEnvironment.objects.create(name="Test Env", project_root="C:/Project", engine_root="C:/UE5", is_active=True)
        profile = BuildProfile.objects.create(name="Tracked", headless=True)
        run = PipelineRun.objects.create(profile=profile)
        
        mock_run.return_value = mock.Mock(returncode=0, stdout="Mock output")
        
        run_headless_tests_task(run.id)
        
        self.assertEqual(run.steps.count(), 1)
        step = run.steps.first()
        self.assertEqual(step.step_name, "Headless Validator")
        self.assertEqual(step.status, "SUCCESS")
        self.assertIn("Mock output", step.logs)

    @mock.patch('subprocess.run')
    def test_staging_build_task(self, mock_run):
        """Test that the staging builder generates the correct UAT command."""
        # Setup environment
        env = ProjectEnvironment.objects.create(
            name="Test Env Staging",
            project_root="C:/Project",
            engine_root="C:/UE5",
            staging_dir="C:/Project/Saved/StagedBuilds",
            is_active=True
        )
        
        # Mock successful run
        mock_run.return_value = mock.Mock(returncode=0)
        
        # Run task
        run_staging_build_task()
        
        # Assert subprocess.run was called with correct arguments
        # We expect RunUAT.bat BuildCookRun, project path, and staging flags
        args, kwargs = mock_run.call_args
        cmd = args[0]
        
        self.assertIn("BuildCookRun", cmd)
        self.assertIn("-build", cmd)
        self.assertIn("-cook", cmd)
        self.assertIn("-stage", cmd)
        self.assertIn("-pak", cmd)
        self.assertIn(f"-stagingdirectory={env.staging_dir}", cmd)

    def test_orchestrator_chain_generation(self):
        """Test that the orchestrator creates the correct Celery chain based on profile."""
        profile = BuildProfile.objects.create(
            name="Full Pipeline",
            headless=True,
            staging=True
        )
        run = PipelineRun.objects.create(profile=profile)
        
        chain = orchestrate_pipeline(profile.id, run.id)
        
        # chain.tasks should contain signatures for both tasks + finalize
        self.assertEqual(len(chain.tasks), 3)
        self.assertEqual(chain.tasks[0].task, "pipelines.tasks.run_headless_tests_task")
        self.assertEqual(chain.tasks[1].task, "pipelines.tasks.run_staging_build_task")
        self.assertEqual(chain.tasks[2].task, "pipelines.tasks.finalize_pipeline_run")

    def test_orchestrator_skips_headless(self):
        """Test that the orchestrator skips headless if disabled in profile."""
        profile = BuildProfile.objects.create(
            name="Staging Only",
            headless=False,
            staging=True
        )
        
        chain = orchestrate_pipeline(profile.id)
        
        # Should only have staging task
        self.assertEqual(len(chain.tasks), 1)
        self.assertEqual(chain.tasks[0].task, "pipelines.tasks.run_staging_build_task")
