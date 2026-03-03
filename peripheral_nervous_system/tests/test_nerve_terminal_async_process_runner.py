import asyncio
import sys

import pytest

from peripheral_nervous_system.nerve_terminal import AsyncProcessRunner

# Apply Windows Proactor loop policy for subprocess support
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@pytest.mark.asyncio
async def test_process_runner_success():
    """Verify standard stdout streaming and exit codes."""
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
    """Verify non-zero exit codes are captured."""
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
    """Verify explicit kill functionality."""
    # Run a command that lasts long enough to be killed
    if sys.platform == 'win32':
        cmd = ['cmd', '/c', 'ping -n 5 127.0.0.1']
    else:
        cmd = ['sleep', '5']

    runner = AsyncProcessRunner(cmd)
    await runner.start()
    assert runner.is_running is True

    runner.kill()

    # Wait for it to die
    exit_code = await runner.wait()

    # It should not be running anymore
    assert runner.is_running is False
    # Exit code varies by platform on kill, but shouldn't be None
    assert exit_code is not None
