from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hydra.models import HydraHeadStatus
from hydra.spells.spell_casters.generic_spell_caster import GenericSpellCaster
from talos_agent.talos_agent import TalosAgentConstants, TalosEvent


# Helper to mock async generators (since MagicMock doesn't do __aiter__ by default)
async def mock_event_stream(events):
    for event in events:
        yield event


@pytest.mark.django_db
class TestGenericSpellCaster:
    @pytest.fixture
    def mock_head(self):
        """Creates a mock HydraHead with necessary attributes."""
        head = MagicMock()
        head.id = 1
        head.status_id = HydraHeadStatus.CREATED
        head.target = None  # Default to Local
        head.spell.talos_executable.internal = False
        head.spell.talos_executable.executable = 'TestExe.exe'
        head.spell.talos_executable.log = 'test.log'

        # Mock the DB methods
        head.save = MagicMock()
        head.refresh_from_db = MagicMock()

        # Mock the manager get() to return this head
        with patch('hydra.models.HydraHead.objects.get', return_value=head):
            with patch(
                'hydra.models.HydraHead.objects.select_related',
                return_value=MagicMock(get=lambda id: head),
            ):
                yield head

    @pytest.fixture
    def mock_switches(self):
        with patch(
            'hydra.spells.spell_casters.generic_spell_caster.spell_switches_and_arguments'
        ) as mock:
            mock.return_value = ['-arg1', '-arg2']
            yield mock

    def test_init_starts_execution(self, mock_head, mock_switches):
        """Test that execute() kicks off the process."""
        caster = GenericSpellCaster(mock_head.id)

        # Mock TalosAgent.execute_local to return an empty stream then exit
        events = [
            TalosEvent(type=TalosAgentConstants.T_LOG, text='Starting...'),
            TalosEvent(type=TalosAgentConstants.T_EXIT, code=0),
        ]

        with patch(
            'talos_agent.talos_agent.TalosAgent.execute_local'
        ) as mock_exec:
            mock_exec.return_value = mock_event_stream(events)

            caster.execute()

            # Verify we called the new API
            mock_exec.assert_called_once()
            args, kwargs = mock_exec.call_args
            assert kwargs['command'] == ['TestExe.exe', '-arg1', '-arg2']
            assert kwargs['log_path'] == 'test.log'

    def test_async_pipeline_success(self, mock_head, mock_switches):
        """Test a successful run updates status to SUCCESS."""
        caster = GenericSpellCaster(mock_head.id)

        events = [
            TalosEvent(
                type=TalosAgentConstants.T_LOG,
                text='Working...',
                source='stdout',
            ),
            TalosEvent(
                type=TalosAgentConstants.T_LOG, text='File log', source='file'
            ),
            TalosEvent(type=TalosAgentConstants.T_EXIT, code=0),
        ]

        with patch(
            'talos_agent.talos_agent.TalosAgent.execute_local'
        ) as mock_exec:
            mock_exec.return_value = mock_event_stream(events)

            caster.execute()

            # Check status update
            assert mock_head.status_id == HydraHeadStatus.SUCCESS

    def test_async_pipeline_failure(self, mock_head, mock_switches):
        """Test a non-zero exit code updates status to FAILED."""
        caster = GenericSpellCaster(mock_head.id)

        events = [
            TalosEvent(type=TalosAgentConstants.T_LOG, text='Crashing...'),
            TalosEvent(type=TalosAgentConstants.T_EXIT, code=1),
        ]

        with patch(
            'talos_agent.talos_agent.TalosAgent.execute_local'
        ) as mock_exec:
            mock_exec.return_value = mock_event_stream(events)

            caster.execute()

            assert mock_head.status_id == HydraHeadStatus.FAILED

    def test_remote_execution_routing(self, mock_head, mock_switches):
        """Test that if target is present, we call execute_remote instead."""
        # Setup Remote Target
        mock_head.target = MagicMock()
        mock_head.target.hostname = '192.168.1.50'

        caster = GenericSpellCaster(mock_head.id)

        events = [TalosEvent(type=TalosAgentConstants.T_EXIT, code=0)]

        with patch(
            'talos_agent.talos_agent.TalosAgent.execute_remote'
        ) as mock_remote:
            mock_remote.return_value = mock_event_stream(events)

            caster.execute()

            mock_remote.assert_called_once()
            # Verify we passed the hostname
            assert mock_remote.call_args[1]['target_hostname'] == '192.168.1.50'

    def test_command_quoting_logic(self, mock_head):
        """Test arguments are passed correctly (Agent handles quoting now, but list integrity matters)."""
        mock_head.spell.talos_executable.executable = 'RunUAT.bat'

        with patch(
            'hydra.spells.spell_casters.generic_spell_caster.spell_switches_and_arguments'
        ) as mock_sw:
            mock_sw.return_value = ['-project="C:\\My Files\\Proj.uproject"']

            caster = GenericSpellCaster(mock_head.id)

            events = [TalosEvent(type=TalosAgentConstants.T_EXIT, code=0)]

            with patch(
                'talos_agent.talos_agent.TalosAgent.execute_local'
            ) as mock_exec:
                mock_exec.return_value = mock_event_stream(events)

                caster.execute()

                # Check the list passed to the agent
                expected_cmd = [
                    'RunUAT.bat',
                    '-project="C:\\My Files\\Proj.uproject"',
                ]
                mock_exec.assert_called_once()
                assert mock_exec.call_args[1]['command'] == expected_cmd
