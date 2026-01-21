import os
from unittest import mock
from django.test import TestCase
from hydra.models import (
    HydraHead, HydraHeadStatus, HydraSpawn, HydraSpellbook, HydraSpell, 
    HydraExecutable, HydraSpawnStatus, HydraEnvironment
)
from hydra.tasks import stream_command_to_db
from environments.models import ProjectEnvironment

class TaskExecutionTest(TestCase):
    fixtures = [
        'talos_frontal/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json',
        'environments/fixtures/initial_data.json',
        'talos_reasoning/fixtures/initial_data.json'
    ]
    def setUp(self):
        # 1. Setup minimal DB state
        self.env = ProjectEnvironment.objects.create(
            name="ExecTestEnv",
            project_root="C:/FakeProject",
            engine_root="C:/UE5",
            build_root="C:/Builds",
            is_active=True
        )
        self.hydra_env = HydraEnvironment.objects.create(project_environment=self.env)
        
        self.status_created = HydraHeadStatus.objects.first()
        self.status_running = HydraHeadStatus.objects.get(name='Running')
        self.status_failed = HydraHeadStatus.objects.get(name='Failed')
        self.spawn_status = HydraSpawnStatus.objects.first()

        self.exe = HydraExecutable.objects.create(name="TestExe", slug="test", path_template="echo")
        self.spell = HydraSpell.objects.create(name="TestSpell", executable=self.exe)
        self.book = HydraSpellbook.objects.create(name="TestBook")
        
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, 
            environment=self.hydra_env, 
            status=self.spawn_status
        )
        
        self.head = HydraHead.objects.create(
            spawn=self.spawn, 
            spell=self.spell, 
            status=self.status_created
        )

    @mock.patch('hydra.tasks.subprocess.Popen')
    def test_system_logs_are_written(self, mock_popen):
        """
        Verifies that 'execution_log' is populated with PID, CWD, and Timestamps.
        """
        # Mock Process Behavior
        process_mock = mock.Mock()
        process_mock.pid = 12345
        process_mock.returncode = 0
        process_mock.poll.side_effect = [None, 0] # Alive once, then dead
        process_mock.stdout.readline.side_effect = ["Log output line 1\n", ""]
        
        # Context Manager mocks
        process_mock.stdout.__enter__ = mock.Mock(return_value=process_mock.stdout)
        process_mock.stdout.__exit__ = mock.Mock(return_value=None)
        
        mock_popen.return_value = process_mock

        # Run Execution
        cmd = ["echo", "hello"]
        stream_command_to_db(cmd, self.head)

        # Refresh Data
        self.head.refresh_from_db()

        # Assert System Log Content (The new feature)
        log = self.head.execution_log
        print(f"\n[TEST LOG CONTENT]:\n{log}")

        self.assertIn("Initializing Process...", log)
        self.assertIn("Command constructed (2 tokens)", log)
        self.assertIn("Working Directory: C:/FakeProject", log.replace("\\", "/"))
        self.assertIn("Process Spawned. PID: 12345", log)
        self.assertIn("Process finished with Exit Code: 0", log)

    @mock.patch('hydra.tasks.subprocess.Popen')
    def test_fatal_launch_failure_is_logged(self, mock_popen):
        """
        Verifies that if the process fails to start (e.g. missing exe),
        the error is logged to execution_log and status is set to FAILED.
        """
        # Simulate FileNotFoundError
        mock_popen.side_effect = FileNotFoundError("Executable not found")

        cmd = ["bad_command.exe"]
        stream_command_to_db(cmd, self.head)

        self.head.refresh_from_db()

        # Assert Failure State
        self.assertEqual(self.head.status_id, HydraHeadStatus.FAILED)
        
        # Assert Log Content
        self.assertIn("FATAL ERROR: Failed to launch process", self.head.execution_log)
        self.assertIn("Executable not found", self.head.execution_log)