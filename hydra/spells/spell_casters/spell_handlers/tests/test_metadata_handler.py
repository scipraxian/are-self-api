import json
import os
from unittest.mock import mock_open, patch

from django.test import TestCase

from environments.models import TalosExecutable
from hydra.models import (
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpawnStatus,
    HydraSpell,
    HydraSpellbook,
)
from hydra.spells.spell_casters.spell_handlers.spell_handler_codes import (
    HANDLER_INTERNAL_ERROR_CODE,
    HANDLER_SUCCESS_CODE,
    HANDLER_WRITE_ERROR_CODE,
)
from hydra.spells.spell_casters.spell_handlers.version_metadata_handler import (
    update_version_metadata,)

MODULE_PATH = (
    'hydra.spells.spell_casters.spell_handlers.version_metadata_handler')


class VersionMetadataHandlerTest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'hydra/fixtures/initial_data.json',
    ]

    def setUp(self):
        self.status_running = HydraHeadStatus.objects.get(
            id=HydraHeadStatus.RUNNING)
        self.spawn_running = HydraSpawnStatus.objects.get(
            id=HydraSpawnStatus.RUNNING)

        self.spell = HydraSpell.objects.create(
            name='Version Spell',
            talos_executable_id=TalosExecutable.VERSION_HANDLER,
        )
        self.book = HydraSpellbook.objects.create(name='Test Book')

        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, status_id=HydraSpawnStatus.RUNNING)

        self.head = HydraHead.objects.create(
            spawn=self.spawn,
            spell=self.spell,
            status_id=HydraHeadStatus.RUNNING,
        )

    @patch(f'{MODULE_PATH}.spell_switches_and_arguments')
    @patch(f'{MODULE_PATH}.log_system')  # Mute DB logging for speed
    def test_creates_new_file_if_missing(self, mock_log, mock_resolve):
        """Verify it creates a fresh JSON file if one doesn't exist."""
        target_path = 'C:/Fake/Content/AppVersion.json'
        mock_resolve.return_value = target_path

        # Mock OS operations
        with (
                patch('os.path.exists') as mock_exists,
                patch('os.makedirs') as mock_mkdirs,
                patch('builtins.open', new_callable=mock_open) as mock_file,
                patch(f'{MODULE_PATH}.getpass.getuser',
                      return_value='TestBuilder'),
        ):
            # 1. Directory exists, File does not
            def exists_side_effect(path):
                if path == os.path.dirname(target_path):
                    return True
                if path == target_path:
                    return False
                return False

            mock_exists.side_effect = exists_side_effect

            # Execute
            code, log = update_version_metadata(self.head.id)

            # Verify
            self.assertEqual(code, HANDLER_SUCCESS_CODE)
            self.assertIn('[SUCCESS]', log)

            # Check Write Content
            handle = mock_file()
            # Aggregate all write calls to handle json.dump chunking
            written_content = ''.join(
                call.args[0] for call in handle.write.call_args_list)
            written_data = json.loads(written_content)

            self.assertIn('Build', written_data)
            self.assertEqual(written_data['Build']['Builder'], 'TestBuilder')
            self.assertEqual(written_data['Game']['Name'], 'HSH: Vacancy')

    @patch(f'{MODULE_PATH}.spell_switches_and_arguments')
    @patch(f'{MODULE_PATH}.log_system')
    def test_updates_existing_file_preserving_data(self, mock_log,
                                                   mock_resolve):
        """Verify it updates 'Build' block but keeps existing 'Game' config."""
        target_path = 'C:/Fake/AppVersion.json'
        mock_resolve.return_value = [target_path]

        existing_content = json.dumps({
            'Game': {
                'Name': 'ExistingGame',
                'Major': 9,
                'Minor': 9,
                'Patch': 9,
            },
            'OldBuild': 'LegacyData',
        })

        with (
                patch('os.path.exists', return_value=True),
                patch(
                    'builtins.open',
                    new_callable=mock_open,
                    read_data=existing_content,
                ) as mock_file,
        ):
            code, log = update_version_metadata(self.head.id)

            self.assertEqual(code, HANDLER_SUCCESS_CODE)

            # Get the data written back to the file
            handle = mock_file()
            written_content = ''.join(
                call.args[0] for call in handle.write.call_args_list)
            data = json.loads(written_content)

            # Assertions
            self.assertEqual(data['Game']['Major'], 9,
                             'Should preserve existing Game data')
            self.assertIn('Build', data, 'Should inject Build block')
            self.assertIn('OldBuild', data, 'Should preserve unrelated keys')

    @patch(f'{MODULE_PATH}.spell_switches_and_arguments')
    @patch(f'{MODULE_PATH}.log_system')
    def test_recovers_from_corrupt_json(self, mock_log, mock_resolve):
        """Verify it handles broken JSON by re-initializing the file."""
        target_path = 'C:/Fake/Corrupt.json'
        mock_resolve.return_value = [target_path]

        with (
                patch('os.path.exists', return_value=True),
                patch(
                    'builtins.open',
                    new_callable=mock_open,
                    read_data='{ bad_json: ',
                ) as mock_file,
        ):
            code, log = update_version_metadata(self.head.id)

            self.assertEqual(code, HANDLER_SUCCESS_CODE)
            self.assertIn('is corrupt', log)

            # Verify it wrote a fresh valid structure
            handle = mock_file()
            written_content = ''.join(
                call.args[0] for call in handle.write.call_args_list)
            data = json.loads(written_content)
            self.assertEqual(data['Game']['Name'], 'HSH: Vacancy')

    @patch(f'{MODULE_PATH}.spell_switches_and_arguments')
    @patch(f'{MODULE_PATH}.log_system')
    def test_handles_directory_creation_failure(self, mock_log, mock_resolve):
        """Verify it returns specific error code if directory creation fails."""
        target_path = 'Z:/Protected/AppVersion.json'
        mock_resolve.return_value = target_path

        # FIX: Raise OSError instead of PermissionError to hit the generic catch block
        # which returns HANDLER_WRITE_ERROR_CODE and logs "Could not create directory"
        with (
                patch('os.path.exists', return_value=False),
                patch('os.makedirs', side_effect=OSError('Generic OS Failure')),
        ):
            code, log = update_version_metadata(self.head.id)

            self.assertEqual(code, HANDLER_WRITE_ERROR_CODE)
            self.assertIn('Could not create directory', log)

    @patch(f'{MODULE_PATH}.spell_switches_and_arguments')
    @patch(f'{MODULE_PATH}.log_system')
    def test_handles_file_write_failure(self, mock_log, mock_resolve):
        """Verify it returns internal error code if file write fails."""
        target_path = 'C:/Locked/AppVersion.json'
        mock_resolve.return_value = target_path

        # FIX: Set exists=False. This skips the 'read' block (which catches OSError)
        # and forces execution into the 'write' block, where the side_effect triggers.
        with (
                patch('os.path.exists', return_value=False),
                patch('builtins.open', side_effect=IOError('Disk Full')),
        ):
            code, log = update_version_metadata(self.head.id)

            self.assertEqual(code, HANDLER_INTERNAL_ERROR_CODE)
            self.assertIn('Version Stamp Failed', log)
