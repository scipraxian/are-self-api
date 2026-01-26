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
    head.spell.talos_executable.executable = 'UnrealEditor-Cmd.exe'
    head.spell.talos_executable.log = 'C:/Logs/Test.log'
    head.spell.talos_executable.internal = False

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
        mock_head.spell.talos_executable.internal = False

        with patch(
            'hydra.spells.spell_casters.generic_spell_caster.run_hydra_pipeline'
        ) as mock_pipeline:
            mock_pipeline.return_value = 0

            # FIX: Patch the SYNC method, not the async one
            with patch.object(
                GenericSpellCaster, '_load_head_sync'
            ) as mock_load:
                mock_load.return_value = None

                caster = GenericSpellCaster(mock_head.id)
                caster.head = mock_head
                caster.spell = mock_head.spell

                caster.execute()

                mock_pipeline.assert_called_once()

    def test_async_pipeline_success(self, mock_head, mock_switches):
        mock_head.spell.talos_executable.internal = False

        with patch(
            'hydra.spells.spell_casters.generic_spell_caster.run_hydra_pipeline'
        ) as mock_pipeline:
            mock_pipeline.return_value = 0

            with patch.object(
                GenericSpellCaster, '_load_head_sync'
            ) as mock_load:
                mock_load.return_value = None

                caster = GenericSpellCaster(mock_head.id)
                caster.head = mock_head
                caster.spell = mock_head.spell

                caster.execute()

                # Verify calling save (success update)
                assert mock_head.save.called

    def test_async_pipeline_failure(self, mock_head, mock_switches):
        mock_head.spell.talos_executable.internal = False

        with patch(
            'hydra.spells.spell_casters.generic_spell_caster.run_hydra_pipeline'
        ) as mock_pipeline:
            mock_pipeline.return_value = 255

            with patch.object(
                GenericSpellCaster, '_load_head_sync'
            ) as mock_load:
                mock_load.return_value = None

                caster = GenericSpellCaster(mock_head.id)
                caster.head = mock_head
                caster.spell = mock_head.spell

                caster.execute()

                # Check that we set status to FAILED (6)
                assert caster.status == 6

    def test_command_quoting_logic(self, mock_head):
        mock_head.spell.talos_executable.internal = False
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
                    GenericSpellCaster, '_load_head_sync'
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
