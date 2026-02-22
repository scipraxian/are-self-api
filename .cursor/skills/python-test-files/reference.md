# Python Test Files — Reference

## Condensed Rules (from styling + engineering standards)

- **Imports**: stdlib → third-party → local, blank line between groups; no wildcards; no local imports inside functions.
- **DB tests**: `django.test.TestCase`, `@pytest.mark.django_db` on class or test; `fixtures = ['app/fixtures/...']` or create in `setUp`; never write to live DB; do not use `manage.py migrate` in tests.
- **Setup**: Pytest fixtures or TestCase `setUp`; separate setup from assertions (D.8.2).
- **Parametrize**: Use `@pytest.mark.parametrize` for multiple input/expected pairs.
- **Names**: Long and descriptive; e.g. `test_run_hydra_pipeline_leash_broken`.
- **Docstrings**: One sentence preferred; start with "Assert", "Verify", or "Ensure"; for critical behavior add "CRITICAL: ...".
- **Determinism**: No wall-clock, network, or live DB; use mocks, fixtures, `tmp_path`.
- **Scope**: Test project logic only; do not test framework, hardware, DB, network, OS, external services.
- **Async on Windows**: Set `asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())` when testing async code.

---

## Codebase Examples

### 1. Async fixture + @pytest.mark.asyncio (talos_agent/tests/test_talos_agent.py)

```python
import asyncio
import sys

import pytest

from talos_agent.talos_agent import TalosAgent, TalosAgentConstants

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@pytest.fixture
async def agent_server(unused_tcp_port):
    """
    Async fixture that starts the TalosAgent server in a background task.
    """
    agent = TalosAgent(port=unused_tcp_port)
    server_task = asyncio.create_task(agent.run_server())
    await asyncio.sleep(0.1)
    yield agent
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_ping(agent_server):
    responses = await send_command_async(
        agent_server.port, TalosAgentConstants.CMD_PING
    )
    assert len(responses) == 1
    assert responses[0][TalosAgentConstants.K_STATUS] == TalosAgentConstants.S_PONG
```

### 2. Django TestCase + fixtures + setUp + @pytest.mark.django_db (hydra/tests/test_serializers.py)

```python
import pytest
from django.test import TestCase

from hydra.models import HydraSpellbook, HydraSpellbookNode, ...
from hydra.serializers import HydraSpawnCreateSerializer, ...


@pytest.mark.django_db
class HydraSerializersTest(TestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'hydra/fixtures/initial_data.json',
    ]

    def setUp(self):
        self.book = HydraSpellbook.objects.create(name='Book A')
        self.spell = HydraSpell.objects.create(...)
        self.node_a1 = HydraSpellbookNode.objects.create(
            spellbook=self.book, spell=self.spell
        )

    def test_spawn_create_validation(self):
        """Verify Launch Request validation."""
        valid_data = {'spellbook_id': self.book.id}
        serializer = HydraSpawnCreateSerializer(data=valid_data)
        self.assertTrue(serializer.is_valid())

    def test_wire_integrity_validation(self):
        """Ensure wires cannot connect nodes from different spellbooks."""
        invalid_data = {..., 'target': self.node_b1.id}
        serializer = HydraSpellbookConnectionWireSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('Target node does not belong', str(serializer.errors))
```

### 3. TestCase + fixtures + mocks (talos_reasoning/tests/test_integration.py)

```python
from django.test import TestCase
from unittest.mock import patch, MagicMock

from talos_reasoning.engine import ReasoningEngine
from talos_reasoning.models import ReasoningSession, ReasoningGoal, ReasoningStatusID


class EngineSimulationTest(TestCase):
    fixtures = ['talos_reasoning/fixtures/initial_data.json']

    def setUp(self):
        self.session = ReasoningSession.objects.create(
            goal="Test Sandbox", status_id=ReasoningStatusID.ACTIVE
        )
        self.engine = ReasoningEngine()

    @patch('talos_reasoning.engine.OllamaClient')
    def test_chat_scenario_read_manage_py(self, mock_client_cls):
        ReasoningGoal.objects.create(
            session=self.session,
            reasoning_prompt="Read manage.py",
            status_id=ReasoningStatusID.PENDING,
        )
        mock_instance = mock_client_cls.return_value
        mock_instance.chat.side_effect = [
            {"content": "READ_FILE: manage.py"},
            {"content": "Done."},
            {"content": "Summary."},
        ]
        self.engine.tick(self.session.id)
        self.session.refresh_from_db()
        last_turn = self.session.turns.filter(tool_calls__isnull=False).last()
        tool_call = last_turn.tool_calls.first()
        self.assertIn("django", tool_call.result_payload.lower())
```

### 4. pytest.raises + tmp_path + CRITICAL docstring (talos_agent/tests/test_talos_agent_run_hydra_pipeline.py)

```python
import asyncio
import sys
from unittest.mock import patch

import pytest

from talos_agent.talos_agent import run_hydra_pipeline

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@pytest.mark.asyncio
async def test_run_hydra_pipeline_basic(tmp_path):
    script = "import time; print('start', flush=True); time.sleep(0.5); print('end', flush=True)"
    cmd = [sys.executable, '-c', script]
    captured = []
    async def callback(text):
        captured.append(text.strip())
    exit_code = await run_hydra_pipeline(cmd, None, callback)
    assert exit_code == 0
    assert 'start' in captured
    assert 'end' in captured


@pytest.mark.asyncio
async def test_run_hydra_pipeline_leash_broken():
    """
    CRITICAL: Verify that if the callback raises a Network Error,
    the process is killed and the exception bubbles up IMMEDIATELY.
    """
    async def broken_callback(text):
        raise ConnectionResetError('Simulated Network Drop')
    with patch('subprocess.run') as mock_run:
        mock_run.return_value.returncode = 0
        with pytest.raises(ConnectionResetError):
            await asyncio.wait_for(
                run_hydra_pipeline(cmd, None, broken_callback), timeout=5.0
            )
```

### 5. Pytest fixtures for mocks (hydra/spells/spell_casters/tests/test_generic_spell_caster.py)

```python
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase

from hydra.spells.spell_casters.generic_spell_caster import GenericSpellCaster


@pytest.mark.django_db
class TestGenericSpellCaster:
    @pytest.fixture
    def mock_head(self):
        """Creates a mock HydraHead with necessary attributes."""
        head = MagicMock()
        head.id = 1
        head.status_id = HydraHeadStatus.CREATED
        head.spell.get_full_command.return_value = ['TestExe.exe', '-arg1', '-arg2']
        with patch('hydra.models.HydraHead.objects.get', return_value=head):
            yield head

    @pytest.fixture
    def mock_env_utils(self):
        with patch('...get_active_environment') as mock_env, \
             patch('...resolve_environment_context') as mock_ctx:
            mock_env.return_value = None
            mock_ctx.return_value = {}
            yield mock_env, mock_ctx

    def test_init_starts_execution(self, mock_head, mock_env_utils):
        """Test that execute() kicks off the process."""
        caster = GenericSpellCaster(mock_head.id)
        with patch('talos_agent.talos_agent.TalosAgent.execute_local') as mock_exec:
            mock_exec.return_value = mock_event_stream(events)
            caster.execute()
            mock_exec.assert_called_once()
            assert kwargs['command'] == ['TestExe.exe', '-arg1', '-arg2']
```

### 6. Async log monitor with tmp_path (talos_agent/tests/test_talos_agent_async_log_monitor.py)

```python
@pytest.mark.asyncio
async def test_log_monitor_basic(tmp_path):
    log_file = tmp_path / 'test.log'
    log_file.write_text('line 1\n', encoding='utf-8')
    monitor = AsyncLogMonitor(str(log_file), launch_time=time.time() - 100)
    lines = await consume_stream(monitor, timeout=2.0)
    assert 'line 1\n' in lines


@pytest.mark.asyncio
async def test_log_monitor_patience(tmp_path):
    """Test waiting for a file that doesn't exist yet."""
    log_file = tmp_path / 'late.log'
    monitor = AsyncLogMonitor(str(log_file), launch_time=time.time())
    # ... writer creates file after delay; reader eventually sees it
```
