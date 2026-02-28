from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from django.test import TestCase

from environments.models import (
    ProjectEnvironment,
    ProjectEnvironmentStatus,
    ProjectEnvironmentType,
    TalosExecutable,
)
from central_nervous_system.models import (
    HydraHead,
    HydraHeadStatus,
    HydraSpawn,
    HydraSpell,
    HydraSpellbook,
    HydraSpellbookNode,
)
from central_nervous_system.spells.spell_casters.generic_spell_caster import GenericSpellCaster
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
        with patch('central_nervous_system.models.HydraHead.objects.get', return_value=head):
            with patch(
                'central_nervous_system.models.HydraHead.objects.select_related',
                return_value=MagicMock(get=lambda id: head),
            ):
                # Setup default get_full_command return
                head.spell.get_full_command.return_value = [
                    'TestExe.exe',
                    '-arg1',
                    '-arg2',
                ]
                yield head

    @pytest.fixture
    def mock_env_utils(self):
        with (
            patch(
                'central_nervous_system.spells.spell_casters.generic_spell_caster.get_active_environment'
            ) as mock_env,
            patch(
                'central_nervous_system.spells.spell_casters.generic_spell_caster.resolve_environment_context'
            ) as mock_ctx,
        ):
            mock_env.return_value = None
            mock_ctx.return_value = {}
            yield mock_env, mock_ctx

    def test_init_starts_execution(self, mock_head, mock_env_utils):
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

    def test_async_pipeline_success(self, mock_head, mock_env_utils):
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

    def test_async_pipeline_failure(self, mock_head, mock_env_utils):
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

    def test_remote_execution_routing(self, mock_head, mock_env_utils):
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

    def test_command_quoting_logic(self, mock_head, mock_env_utils):
        """Test arguments are passed correctly (Agent handles quoting now, but list integrity matters)."""
        mock_head.spell.talos_executable.executable = 'RunUAT.bat'
        mock_head.spell.get_full_command.return_value = [
            'RunUAT.bat',
            '-project="C:\\My Files\\Proj.uproject"',
        ]

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

    def test_log_path_template_resolution(self, mock_head, mock_env_utils):
        """Verify that templated log paths are resolved before pipeline execution."""
        # 1. Setup a templated log path
        mock_head.spell.talos_executable.log = (
            'C:\\{{project_name}}\\Saved\\Logs\\{{project_name}}.log'
        )

        # 2. Inject context into mock_env_utils (mock_ctx is the 2nd item in fixture)
        _, mock_ctx = mock_env_utils
        mock_ctx.return_value = {'project_name': 'HSHVacancy'}

        caster = GenericSpellCaster(mock_head.id)
        events = [TalosEvent(type=TalosAgentConstants.T_EXIT, code=0)]

        with patch(
            'talos_agent.talos_agent.TalosAgent.execute_local'
        ) as mock_exec:
            mock_exec.return_value = mock_event_stream(events)

            caster.execute()

            # 3. Assertions
            expected_resolved_log = (
                'C:\\HSHVacancy\\Saved\\Logs\\HSHVacancy.log'
            )

            mock_exec.assert_called_once()
            _, kwargs = mock_exec.call_args

            assert kwargs['log_path'] == expected_resolved_log, (
                f'Log path was not resolved! Got: {kwargs["log_path"]}'
            )

    @pytest.mark.asyncio
    async def test_blackboard_exhale_persistence(
        self, mock_head, mock_env_utils
    ):
        """Verify native python tools can mutate memory and the Caster preserves it."""

        # 1. Setup Initial Memory
        mock_head.blackboard = {'state': 'initial'}
        mock_head.save()

        # 2. Mock a native Python Tool (e.g., an AI Parser)
        async def mock_ai_handler(head_id):
            # Native tools interact with the DB directly
            h = await sync_to_async(HydraHead.objects.get)(id=head_id)
            h.blackboard['state'] = 'mutated'
            await sync_to_async(h.save)(update_fields=['blackboard'])
            return 200, 'AI Analysis Complete'

        # 3. Hijack the Caster's Native Handler routing
        with patch.dict(
            'central_nervous_system.spells.spell_casters.generic_spell_caster.NATIVE_HANDLERS',
            {'ai_parser': mock_ai_handler},
        ):
            mock_head.spell.talos_executable.internal = True
            mock_head.spell.talos_executable.executable = 'ai_parser'

            caster = GenericSpellCaster(mock_head.id)
            caster.head = mock_head
            caster.spell = mock_head.spell

            # THE FIX: Use AsyncMock so `await self.logger.flush()` doesn't crash
            caster.logger = AsyncMock()

            # Execute Native Route
            await caster._execute_local_python()

            # 4. Assert the Caster did NOT cause amnesia
            mock_head.refresh_from_db()
            assert mock_head.blackboard.get('state') == 'mutated'

    def test_unified_pipeline_blackboard_interception(
        self, mock_head, mock_env_utils
    ):
        """Verify the Caster intercepts ::blackboard_set, mutates memory, and strips the log."""
        mock_head.blackboard = {}
        mock_head.execution_log = ''
        mock_head.application_log = ''

        caster = GenericSpellCaster(mock_head.id)

        # Mixed log output mimicking a CLI tool sending secret commands
        log_payload = (
            'Standard log line 1\n'
            '::blackboard_set status_msg::All systems nominal\n'
            'Standard log line 2\n'
            '::blackboard_set error_count::0\n'
        )

        events = [
            TalosEvent(
                type=TalosAgentConstants.T_LOG,
                text=log_payload,
                source='stdout',
            ),
            TalosEvent(type=TalosAgentConstants.T_EXIT, code=0),
        ]

        with patch(
            'talos_agent.talos_agent.TalosAgent.execute_local'
        ) as mock_exec:
            mock_exec.return_value = mock_event_stream(events)

            caster.execute()

            # 1. Assert Blackboard Mutations
            assert (
                mock_head.blackboard.get('status_msg') == 'All systems nominal'
            )
            assert mock_head.blackboard.get('error_count') == '0'

            # 2. Assert Log Stripping
            assert '::blackboard_set' not in mock_head.execution_log
            assert 'Standard log line 1' in mock_head.application_log
            assert 'Standard log line 2' in mock_head.application_log

    def test_blackboard_interception_edge_cases(
        self, mock_head, mock_env_utils
    ):
        """Verify robust parsing of ::blackboard_set with weird spacing, empty DB fields, and JSON."""
        mock_head.blackboard = None  # Simulate an uninitialized JSONField
        mock_head.execution_log = ''

        caster = GenericSpellCaster(mock_head.id)

        # Edge cases
        log_payload = (
            '::blackboard_set   weird_spacing  ::  value with spaces  \n'
            '::blackboard_set empty_val::\n'
            '::blackboard_set json_data::{"key": "val", "nested": "data"}\n'
        )

        events = [
            TalosEvent(
                type=TalosAgentConstants.T_LOG,
                text=log_payload,
                source='stdout',
            ),
            TalosEvent(type=TalosAgentConstants.T_EXIT, code=0),
        ]

        with patch(
            'talos_agent.talos_agent.TalosAgent.execute_local'
        ) as mock_exec:
            mock_exec.return_value = mock_event_stream(events)
            caster.execute()

            # Assert Initialization and Extraction
            assert isinstance(mock_head.blackboard, dict)
            assert (
                mock_head.blackboard.get('weird_spacing') == 'value with spaces'
            )
            assert mock_head.blackboard.get('empty_val') == ''
            assert (
                mock_head.blackboard.get('json_data')
                == '{"key": "val", "nested": "data"}'
            )

            # Assert Scrubbing
            assert '::blackboard_set' not in mock_head.execution_log


@pytest.mark.django_db
class GenericSpellCasterQueryTest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'talos_agent/fixtures/initial_data.json',
        'talos_agent/fixtures/test_agents.json',
        'central_nervous_system/fixtures/initial_data.json',
    ]

    def setUp(self):
        # Environment
        env_type = ProjectEnvironmentType.objects.get_or_create(name='UE5')[0]
        env_status = ProjectEnvironmentStatus.objects.get_or_create(
            name='Ready'
        )[0]
        self.env = ProjectEnvironment.objects.create(
            name='Test Env', type=env_type, status=env_status
        )

        # Spell & Node
        self.exe = TalosExecutable.objects.create(
            name='TestExe', executable='cmd.exe'
        )
        self.spell = HydraSpell.objects.create(
            name='TestSpell', talos_executable=self.exe
        )
        self.book = HydraSpellbook.objects.create(name='Test Book')
        self.node = HydraSpellbookNode.objects.create(
            spellbook=self.book, spell=self.spell, environment=self.env
        )

        # Execution
        self.spawn = HydraSpawn.objects.create(
            spellbook=self.book, environment=self.env, status_id=1
        )
        self.head = HydraHead.objects.create(
            spawn=self.spawn, node=self.node, spell=self.spell, status_id=1
        )

    def test_load_head_sync_prefetches_environment(self):
        """Verify _load_head_sync loads the environment in the initial query to prevent async ORM crashes."""
        caster = GenericSpellCaster(head_id=self.head.id)

        # 1. Load the head (Should take exactly 1 query due to select_related)
        with self.assertNumQueries(1):
            caster._load_head_sync()

        # 2. Access the deeply nested relations (Should take 0 additional queries)
        # If any of these throw an error or trigger a query, the async pipeline will crash.
        with self.assertNumQueries(0):
            spawn_env = caster.head.spawn.environment
            node_env = caster.head.node.environment
            target = caster.head.target
            executable = caster.head.spell.talos_executable

        # 3. Assert correct data was cached
        self.assertEqual(spawn_env.id, self.env.id)
        self.assertEqual(node_env.id, self.env.id)
        self.assertEqual(executable.id, self.exe.id)
