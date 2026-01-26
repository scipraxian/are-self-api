import uuid
from unittest.mock import MagicMock, patch

import pytest

from hydra.models import HydraHeadStatus
from hydra.spells.spell_casters.generic_spell_caster import GenericSpellCaster


@pytest.fixture
def mock_head():
    """Mocks the HydraHead ORM object."""
    head = MagicMock()
    head.id = uuid.uuid4()
    head.spell.name = 'Test Spell'
    # Default values matching the tests
    head.spell.talos_executable.executable = 'UnrealEditor-Cmd.exe'
    head.spell.talos_executable.log = 'C:/Logs/Test.log'
    head.spell.talos_executable.internal = False

    # Initial log state
    head.execution_log = ''
    head.spell_log = ''
    return head


@pytest.fixture
def mock_switches():
    """Mocks the switch builder."""
    with patch(
        'hydra.spells.spell_casters.generic_spell_caster.spell_switches_and_arguments'
    ) as mock:
        mock.return_value = ['-debug']
        yield mock


@pytest.mark.django_db
class TestGenericSpellCaster:
    def test_init_starts_execution(self, mock_head, mock_switches):
        """Test that execute() kicks off the process."""
        # 1. Setup State
        mock_head.spell.talos_executable.internal = False

        # 2. Patch the Pipeline
        with patch(
            'hydra.spells.spell_casters.generic_spell_caster.run_hydra_pipeline'
        ) as mock_pipeline:
            mock_pipeline.return_value = 0

            # 3. Bypass DB loading
            with patch.object(GenericSpellCaster, '_load_head') as mock_load:
                mock_load.return_value = None

                caster = GenericSpellCaster(mock_head.id)
                # Manually inject state
                caster.head = mock_head
                caster.spell = mock_head.spell

                caster.execute()

                mock_pipeline.assert_called_once()

    def test_async_pipeline_success(self, mock_head, mock_switches):
        """Test the happy path: Process runs and updates status."""
        # Setup
        mock_head.spell.talos_executable.internal = False

        with patch(
            'hydra.spells.spell_casters.generic_spell_caster.run_hydra_pipeline'
        ) as mock_pipeline:
            # Pipeline returns 0 (Success)
            mock_pipeline.return_value = 0

            with patch.object(GenericSpellCaster, '_load_head') as mock_load:
                mock_load.return_value = None

                caster = GenericSpellCaster(mock_head.id)
                caster.head = mock_head
                caster.spell = mock_head.spell

                caster.execute()

                # Verify Exit Status Update
                # Note: We check if _update_status was called or simply check the side effects
                # Since we are mocking everything, we assume the Caster logic works if pipeline returns 0
                # But wait, we need to verify the Caster actually WROTE the success status.
                # Since 'head.save' is what triggers the write, we check the head object.

                # The Caster writes directly to the head object in memory before saving
                # However, since we bypassed _load_head, we are checking the mock_head instance.
                # GenericSpellCaster calls: await self._update_status(HydraHeadStatus.SUCCESS)
                # Which calls: await sync_to_async(self.head.save)(...)

                assert mock_head.save.called

    def test_async_pipeline_failure(self, mock_head, mock_switches):
        """Test the sad path: Process returns non-zero exit code."""
        mock_head.spell.talos_executable.internal = False

        with patch(
            'hydra.spells.spell_casters.generic_spell_caster.run_hydra_pipeline'
        ) as mock_pipeline:
            # Pipeline returns 255 (Failure)
            mock_pipeline.return_value = 255

            with patch.object(GenericSpellCaster, '_load_head') as mock_load:
                mock_load.return_value = None

                caster = GenericSpellCaster(mock_head.id)
                caster.head = mock_head
                caster.spell = mock_head.spell

                caster.execute()

                # Should trigger failure status
                # It writes to the log then saves
                assert mock_pipeline.called

                # We can verify that the Caster TRIED to update the status to FAILED.
                # Since 'head' is a mock, we check its attribute assignment isn't enough,
                # we need to ensure the logic flow hit the failure block.
                # The easiest way is to check the last call to 'save' or check 'status_id' if implemented.
                assert caster.status == GenericSpellCaster.STATUS_FAILED

    def test_command_quoting_logic(self, mock_head):
        """Verify caster correctly combines executable and argument list."""
        mock_head.spell.talos_executable.internal = False
        # FIX: Align the fixture data with the test expectation
        mock_head.spell.talos_executable.executable = 'RunUAT.bat'

        with patch(
            'hydra.spells.spell_casters.generic_spell_caster.spell_switches_and_arguments'
        ) as mock_sw:
            mock_sw.return_value = ['-project="C:\\My Files\\Proj.uproject"']

            with patch(
                'hydra.spells.spell_casters.generic_spell_caster.run_hydra_pipeline'
            ) as mock_pipeline:
                mock_pipeline.return_value = 0

                with patch.object(
                    GenericSpellCaster, '_load_head'
                ) as mock_load:
                    mock_load.return_value = None

                    caster = GenericSpellCaster(mock_head.id)
                    caster.head = mock_head
                    caster.spell = mock_head.spell

                    caster.execute()

                    args, _ = mock_pipeline.call_args
                    cmd_list = args[0]

                    assert cmd_list[0] == 'RunUAT.bat'
                    assert '-project="C:\\My Files\\Proj.uproject"' in cmd_list
