import json
import socket
import sys
import threading
import time

import pytest

from talos_agent.talos_agent import TalosAgent, TalosAgentConstants


@pytest.fixture
def agent():
    # Find a free port
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()

    agent = TalosAgent(port=port)
    thread = threading.Thread(target=agent.run, daemon=True)
    thread.start()

    # Give it a moment to start
    time.sleep(0.5)
    yield agent
    agent.running = False


def send_command(port, cmd, args=None):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(('127.0.0.1', port))
        payload = {
            TalosAgentConstants.K_CMD: cmd,
            TalosAgentConstants.K_ARGS: args or {},
        }
        s.sendall(
            (json.dumps(payload) + '\n').encode(TalosAgentConstants.ENCODING)
        )

        responses = []
        s.settimeout(5.0)
        try:
            while True:
                data = s.recv(4096)
                if not data:
                    break
                # Split by newline as the protocol sends multiple JSON objects for EXECUTE
                for line in (
                    data.decode(TalosAgentConstants.ENCODING)
                    .strip()
                    .split('\n')
                ):
                    if line:
                        responses.append(json.loads(line))
        except socket.timeout:
            pass
        return responses


def test_ping(agent):
    responses = send_command(agent.port, TalosAgentConstants.CMD_PING)
    assert len(responses) == 1
    assert (
        responses[0][TalosAgentConstants.K_STATUS] == TalosAgentConstants.S_PONG
    )
    assert TalosAgentConstants.K_VER in responses[0]


def test_execute_basic(agent):
    if sys.platform == 'win32':
        exe = 'cmd'
        params = ['/c', 'echo hello from agent']
    else:
        exe = 'echo'
        params = ['hello from agent']

    responses = send_command(
        agent.port,
        TalosAgentConstants.CMD_EXECUTE,
        {'executable': exe, 'params': params},
    )

    # We expect:
    # 1. Launching... log
    # 2. "hello from agent" log
    # 3. Exit code 0

    logs = [
        r[TalosAgentConstants.K_CONTENT]
        for r in responses
        if r.get(TalosAgentConstants.K_TYPE) == TalosAgentConstants.T_LOG
    ]
    exits = [
        r
        for r in responses
        if r.get(TalosAgentConstants.K_TYPE) == TalosAgentConstants.T_EXIT
    ]

    assert any('Launching' in log for log in logs)
    assert any('hello from agent' in log for log in logs)
    assert len(exits) == 1
    assert exits[0][TalosAgentConstants.K_CODE] == 0


def test_unknown_command(agent):
    responses = send_command(agent.port, 'NOT_A_COMMAND')
    assert len(responses) == 1
    assert (
        responses[0][TalosAgentConstants.K_STATUS]
        == TalosAgentConstants.S_ERROR
    )
    assert 'Unknown command' in responses[0][TalosAgentConstants.K_MSG]


def test_update_self(agent, tmp_path):
    # This is a bit dangerous as it overwrites talos_agent.py
    # We should mock __file__ or use a separate test file if possible.
    # But since the agent uses os.path.abspath(__file__), it's hard to spoof without monkeypatching.
    # For now, let's just test the JSON response part of update,
    # but we'll avoid actually running the full update logic in a unit test to prevent collateral damage.
    pass
