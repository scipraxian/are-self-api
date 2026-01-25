import asyncio
import sys

import pytest

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from talos_agent.talos_agent import AsyncProcessRunner


@pytest.mark.asyncio
async def test_process_runner_success():
    # Use 'cmd /c' on Windows for a simple echo test
    if sys.platform == 'win32':
        cmd = ['cmd', '/c', 'echo hello world']
    else:
        cmd = ['echo', 'hello world']

    runner = AsyncProcessRunner(cmd)
    await runner.start()

    output = []
    async for line in runner.stream_output():
        output.append(line.strip())

    exit_code = await runner.wait()

    assert 'hello world' in output
    assert exit_code == 0
    assert runner.is_running is False


@pytest.mark.asyncio
async def test_process_runner_error():
    if sys.platform == 'win32':
        cmd = ['cmd', '/c', 'exit 1']
    else:
        cmd = ['sh', '-c', 'exit 1']

    runner = AsyncProcessRunner(cmd)
    await runner.start()

    exit_code = await runner.wait()
    assert exit_code == 1


@pytest.mark.asyncio
async def test_process_runner_kill():
    if sys.platform == 'win32':
        cmd = ['cmd', '/c', 'pause']
    else:
        cmd = ['sleep', '10']

    runner = AsyncProcessRunner(cmd)
    await runner.start()
    assert runner.is_running is True

    runner.kill()
    exit_code = await runner.wait()
    # On Windows, kill() usually results in 1 or some other code,
    # but we just want to ensure it's not running anymore.
    assert runner.is_running is False
