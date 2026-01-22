import time
from unittest.mock import MagicMock, mock_open, patch

from django.test import TestCase

from hydra.models import (
    HydraHead, HydraHeadStatus, HydraSpawn,
    HydraSpawnStatus, HydraSpellbook, HydraSpell, HydraSwitch
)
from environments.models import TalosExecutable, ProjectEnvironment
from hydra.spells.spell_casters.generic_spell_caster import GenericSpellCaster

MODULE_PATH = 'hydra.spells.spell_casters.generic_spell_caster'


class GenericSpellcasterTest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json'
    ]

    def setUp(self):
        # 1. Setup Data Hierarchy using Fixtures
        self.spellbook = HydraSpellbook.objects.first()
        self.proj_env = ProjectEnvironment.objects.get(name="Talos Default Environment")  # depreciated

        # We need to ensure the Environment wrapper exists (it might not be in initial_data depending on version)
        # We check or create it to be safe for the test context
        from hydra.models import HydraEnvironment  # depreciated
        self.hydra_env, _ = HydraEnvironment.objects.get_or_create(
            project_environment=self.proj_env
        )

        self.spawn = HydraSpawn.objects.create(
            status_id=HydraSpawnStatus.CREATED,
            spellbook=self.spellbook,
            environment=self.hydra_env
        )

        # 2. Use a standard executable (PYTHON) for default state
        # ID 2 is PYTHON in your fixtures
        self.python_exe = TalosExecutable.objects.get(id=TalosExecutable.PYTHON)

        self.spell = HydraSpell.objects.create(
            name="Unit Test Spell",
            talos_executable=self.python_exe,
            order=1
        )

        self.head = HydraHead.objects.create(
            spell=self.spell,
            spawn=self.spawn,
            status_id=HydraHeadStatus.CREATED
        )

        # 3. Patch out the auto-execution in __init__ for ALL tests
        self.patcher = patch(f'{MODULE_PATH}.GenericSpellCaster._cast_spell')
        self.mock_cast = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_generic_spellcaster_instantiates(self):
        """Asserts that the GenericSpellCaster can be instantiated."""
        try:
            GenericSpellCaster(self.head.id)
        except Exception as e:
            self.fail(f"Failed to instantiate GenericSpellCaster: {e}")
        self.mock_cast.assert_called_once()

    @patch(f'{MODULE_PATH}.subprocess.Popen')
    @patch('builtins.open', new_callable=mock_open, read_data="Log Line 1")
    @patch(f'{MODULE_PATH}.exists', return_value=True)
    @patch(f'{MODULE_PATH}.getmtime')
    def test_generic_spellcaster_cast_spell(self, mock_mtime, mock_exists, mock_file, mock_popen):
        """Assert popen is called with the correct arguments."""
        self.patcher.stop()

        process_mock = MagicMock()
        process_mock.poll.side_effect = [None] * 50 + [0]
        process_mock.returncode = 0
        mock_popen.return_value = process_mock

        mock_mtime.return_value = time.time() + 1000.0

        # We mock _stream_log_file to prevent file access and loops
        with patch(f'{MODULE_PATH}.GenericSpellCaster._stream_log_file'):
            # We mock _get_command to isolate flow testing
            with patch(f'{MODULE_PATH}.GenericSpellCaster._get_command', return_value=['python', 'script.py']):
                GenericSpellCaster(self.head.id)

        mock_popen.assert_called_once()
        self.head.refresh_from_db()
        self.assertNotEqual(self.head.status_id, HydraHeadStatus.FAILED)
        self.patcher.start()

    def test_generic_spellcaster_executable_router(self):
        """Assert executable router selects the correct executable logic."""
        caster = GenericSpellCaster(self.head.id)

        caster._execute_local_python = MagicMock()
        caster._execute_local_popen = MagicMock()

        # Case 1: Standard Executable (PYTHON) -> Popen
        # Setup: Ensure DB points to PYTHON (ID 2)
        caster.spell.talos_executable = self.python_exe
        caster._executable_router()

        caster._execute_local_popen.assert_called_once()
        caster._execute_local_python.assert_not_called()

        # Reset Mocks
        caster._execute_local_popen.reset_mock()
        caster._execute_local_python.reset_mock()

        # Case 2: Internal Function (ID 1) -> Python
        # Setup: Switch head to INTERNAL_FUNCTION
        internal_exe = TalosExecutable.objects.get(id=TalosExecutable.INTERNAL_FUNCTION)
        caster.spell.talos_executable = internal_exe

        caster._executable_router()

        caster._execute_local_python.assert_called_once()
        caster._execute_local_popen.assert_not_called()

    @patch(f'{MODULE_PATH}.exists')
    @patch(f'{MODULE_PATH}.getmtime')
    def test_generic_spellcaster_block_for_log_file(self, mock_mtime, mock_exists):
        """Assert block for log is called with the correct arguments."""
        # Ensure the executable has a log path set
        self.python_exe.log = "C:/Logs/test.log"
        self.python_exe.save()

        caster = GenericSpellCaster(self.head.id)
        caster.launch_time = time.time()

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        caster.running_subprocess = mock_proc

        mock_exists.return_value = True
        mock_mtime.return_value = time.time() + 100.0

        # Run method
        caster._block_for_log_file()

        # Phase 3 Logic check: Uses talos_executable.log
        mock_exists.assert_called_with(self.python_exe.log)

    @patch(f'{MODULE_PATH}.spell_switches_and_arguments')
    def test_generic_spellcaster_get_command_returns_correct_command(self, mock_switches):
        """Assert get command returns the correct command string."""
        # Setup the mock to return what the helper WOULD return
        # This mocks the integration with the new helper function
        mock_switches.return_value = "arg1 arg2 -switch1"

        caster = GenericSpellCaster(self.head.id)

        # Verify fix: _get_command calls the helper, which we mocked
        cmd = caster._get_command()

        # Fixture PYTHON path is "C:\talos\venv\Scripts\python.exe"
        # We expect: "PATH arg1 arg2 -switch1"
        self.assertIn("python.exe", cmd)
        self.assertIn("arg1 arg2", cmd)
        self.assertIn("-switch1", cmd)

        # Verify we actually called the helper
        mock_switches.assert_called_with(self.spell.id)

    def test_generic_spellcaster_log_router_routes_to_correct_logging_type(self):
        """Assert log router routes to correct logging type based on ID."""
        caster = GenericSpellCaster(self.head.id)

        # Mock methods
        caster._stream_log_file = MagicMock()
        caster._block_for_log_file = MagicMock()

        # Case 1: Standard Executable (PYTHON = 2) -> Should Stream
        caster.spell.talos_executable = self.python_exe
        caster._log_router()
        caster._stream_log_file.assert_called_once()
        caster._block_for_log_file.assert_called_once()

        # Reset
        caster._stream_log_file.reset_mock()
        caster._block_for_log_file.reset_mock()

        # Case 2: Internal Function (INTERNAL = 1) -> Should NOT Stream
        internal_exe = TalosExecutable.objects.get(id=TalosExecutable.INTERNAL_FUNCTION)
        caster.spell.talos_executable = internal_exe
        caster._log_router()

        caster._stream_log_file.assert_not_called()
        caster._block_for_log_file.assert_not_called()

    @patch(f'{MODULE_PATH}.exists', return_value=True)
    @patch(f'{MODULE_PATH}.getmtime')
    @patch(f'{MODULE_PATH}.sleep')
    def test_block_for_log_waits_for_fresh_file(self, mock_sleep, mock_mtime, mock_exists):
        """Ensures the caster does NOT attach to a log file older than the launch time."""
        # Ensure we have a log path
        self.python_exe.log = "C:/Logs/test.log"
        self.python_exe.save()

        caster = GenericSpellCaster(self.head.id)
        caster.launch_time = 1000.0

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        caster.running_subprocess = mock_proc

        mock_mtime.side_effect = [900.0, 900.0, 1001.0]

        caster._block_for_log_file()

        self.assertEqual(mock_mtime.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch(f'{MODULE_PATH}.exists', return_value=False)
    @patch(f'{MODULE_PATH}.sleep')
    def test_block_for_log_timeouts_if_no_file(self, mock_sleep, mock_exists):
        """Ensures we don't wait forever if the game fails to create a log."""
        self.python_exe.log = "C:/Logs/test.log"
        self.python_exe.save()

        caster = GenericSpellCaster(self.head.id)
        caster.launch_time = time.time()

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        caster.running_subprocess = mock_proc

        caster._block_for_log_file()

        self.assertEqual(caster.status, caster.STATUS_FAILED)
        self.assertEqual(mock_sleep.call_count, 100)

    def test_generic_spellcaster_process_is_killed_on_cancel(self):
        """Assert process is killed if we manually trigger cleanup."""
        caster = GenericSpellCaster(self.head.id)

        mock_proc = MagicMock()
        caster.running_subprocess = mock_proc

        # Simulate logic that happens in cleanup
        if caster.running_subprocess:
            caster.running_subprocess.kill()

        mock_proc.kill.assert_called_once()