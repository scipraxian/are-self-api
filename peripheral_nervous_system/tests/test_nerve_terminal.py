import asyncio
import json
import sys

import pytest

from peripheral_nervous_system.nerve_terminal import NerveTerminal, NerveTerminalConstants

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@pytest.fixture
async def agent_server(unused_tcp_port):
    """
    Async fixture that starts the NerveTerminal server in a background task.
    """
    agent = NerveTerminal(port=unused_tcp_port)

    # Run server in background task
    server_task = asyncio.create_task(agent.run_server())

    # Give it a moment to bind
    await asyncio.sleep(0.1)

    yield agent

    # Cleanup
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass


async def send_command_async(port, cmd, args=None):
    """Async client to talk to the agent."""
    reader, writer = await asyncio.open_connection('127.0.0.1', port)

    payload = {
        NerveTerminalConstants.K_CMD: cmd,
        NerveTerminalConstants.K_ARGS: args or {},
    }

    writer.write(
        (json.dumps(payload) + '\n').encode(NerveTerminalConstants.ENCODING)
    )
    await writer.drain()

    responses = []

    # Read until connection closed or timeout
    try:
        while True:
            # Read line by line
            line = await asyncio.wait_for(reader.readline(), timeout=2.0)
            if not line:
                break
            responses.append(json.loads(line.decode().strip()))
    except (asyncio.TimeoutError, ConnectionResetError):
        pass
    finally:
        writer.close()
        await writer.wait_closed()

    return responses


@pytest.mark.asyncio
async def test_ping(agent_server):
    responses = await send_command_async(
        agent_server.port, NerveTerminalConstants.CMD_PING
    )
    assert len(responses) == 1
    assert (
        responses[0][NerveTerminalConstants.K_STATUS] == NerveTerminalConstants.S_PONG
    )


@pytest.mark.asyncio
async def test_execute_basic(agent_server):
    if sys.platform == 'win32':
        exe = 'cmd'
        params = ['/c', 'echo hello agent']
    else:
        exe = 'echo'
        params = ['hello agent']

    responses = await send_command_async(
        agent_server.port,
        NerveTerminalConstants.CMD_EXECUTE,
        {'executable': exe, 'params': params},
    )

    # Filter messages
    logs = [
        r
        for r in responses
        if r.get(NerveTerminalConstants.K_TYPE) == NerveTerminalConstants.T_LOG
    ]
    exits = [
        r
        for r in responses
        if r.get(NerveTerminalConstants.K_TYPE) == NerveTerminalConstants.T_EXIT
    ]

    assert any('Launching' in r[NerveTerminalConstants.K_CONTENT] for r in logs)
    assert any('hello agent' in r[NerveTerminalConstants.K_CONTENT] for r in logs)

    assert len(exits) == 1
    assert exits[0][NerveTerminalConstants.K_CODE] == 0


@pytest.mark.asyncio
async def test_unknown_command(agent_server):
    responses = await send_command_async(agent_server.port, 'BOGUS_CMD')
    assert len(responses) >= 1
    assert (
        responses[0][NerveTerminalConstants.K_STATUS]
        == NerveTerminalConstants.S_ERROR
    )
