import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

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
        # Returns (debug_string, list)
        mock.return_value = ('-debug', ['-debug'])
        yield mock


@pytest.fixture
def mock_runner():
    """Mocks the AsyncProcessRunner."""
    with patch(
        'hydra.spells.spell_casters.generic_spell_caster.AsyncProcessRunner'
    ) as MockClass:
        runner_instance = MockClass.return_value
        runner_instance.start = AsyncMock()
        runner_instance.wait = AsyncMock(return_value=0)  # Default success

        # Mock stream_output as an async iterator
        async def async_gen():
            yield 'Line 1\n'
            yield 'Line 2\n'

        runner_instance.stream_output = lambda: async_gen()

        # Mock process attribute for returncode check
        runner_instance.process = MagicMock()
        runner_instance.process.returncode = 0

        yield runner_instance


@pytest.fixture
def mock_monitor():
    """Mocks the AsyncLogMonitor."""
    with patch(
        'hydra.spells.spell_casters.generic_spell_caster.AsyncLogMonitor'
    ) as MockClass:
        monitor_instance = MockClass.return_value
        # Mock check_for_lines to return data once, then empty
        monitor_instance.check_for_lines = AsyncMock(
            side_effect=[['Game Log Line 1\n'], [], []]
        )
        yield monitor_instance


@pytest.mark.django_db
class TestGenericSpellCaster:
    def test_init_starts_execution(self, mock_head, mock_switches, mock_runner):
        """Test that __init__ kicks off the whole chain."""
        with patch(
            'hydra.models.HydraHead.objects.get', return_value=mock_head
        ):
            GenericSpellCaster(mock_head.id)

            # Verify status update was called multiple times
            assert mock_head.save.call_count >= 1

            # Since the caster is synchronous blocking, it should finish as SUCCESS
            # (mapped from STATUS_COMPLETE)
            assert mock_head.status_id == HydraHeadStatus.SUCCESS

    def test_async_pipeline_success(
        self, mock_head, mock_switches, mock_runner, mock_monitor
    ):
        """Test the happy path: Process runs, logs stream, exits 0."""
        with patch(
            'hydra.models.HydraHead.objects.get', return_value=mock_head
        ):
            GenericSpellCaster(mock_head.id)

            # 1. Check Command Construction
            assert (
                "[LIST] ['UnrealEditor-Cmd.exe', '-debug']"
                in mock_head.execution_log
            )

            # 2. Check Execution Log Streaming (System Output)
            assert 'Line 1' in mock_head.execution_log
            assert 'Line 2' in mock_head.execution_log

            # 3. Check Spell Log Streaming (File Output)
            assert 'Game Log Line 1' in mock_head.spell_log

            # 4. Check Exit Status
            # We set STATUS_COMPLETE (5) at end of cast_spell, which maps to SUCCESS
            assert mock_head.status_id == HydraHeadStatus.SUCCESS
            assert '[EXIT] Success' in mock_head.execution_log

    def test_async_pipeline_failure(
        self, mock_head, mock_switches, mock_runner
    ):
        """Test the sad path: Process returns non-zero exit code."""
        # Setup failure
        mock_runner.wait = AsyncMock(return_value=255)

        with patch(
            'hydra.models.HydraHead.objects.get', return_value=mock_head
        ):
            # We expect NO exception, but a FAILED status
            GenericSpellCaster(mock_head.id)

            assert (
                '[EXIT] Process failed with code 255' in mock_head.execution_log
            )
            assert mock_head.status_id == HydraHeadStatus.FAILED

    def test_command_quoting_logic(self, mock_head):
        """
        Verify that the caster correctly combines the executable and the
        argument list, ensuring safe execution for paths with spaces.
        """
        with patch(
            'hydra.spells.spell_casters.generic_spell_caster.spell_switches_and_arguments'
        ) as mock_sw:
            # Simulate a switch with spaces that was returned as a list item
            mock_sw.return_value = (
                '-project="..."',
                ['-project="C:\\My Files\\Proj.uproject"'],
            )

            with patch(
                'hydra.models.HydraHead.objects.get', return_value=mock_head
            ):
                with patch(
                    'hydra.spells.spell_casters.generic_spell_caster.AsyncProcessRunner'
                ) as MockRunner:
                    # FIX: Make the return value awaitable!
                    instance = MockRunner.return_value
                    instance.start = AsyncMock()
                    instance.wait = AsyncMock(return_value=0)

                    # Mock an empty async iterator for stream_output
                    async def empty_gen():
                        yield ''

                    instance.stream_output = lambda: empty_gen()

                    GenericSpellCaster(mock_head.id)

                    # Verify the list passed to runner contains the specific list item
                    # The second arg to constructor (after self)
                    call_args = MockRunner.call_args[1][
                        'command'
                    ]  # kwargs['command']
                    assert call_args[0] == 'UnrealEditor-Cmd.exe'
                    assert (
                        call_args[1] == '-project="C:\\My Files\\Proj.uproject"'
                    )
                    assert len(call_args) == 2
