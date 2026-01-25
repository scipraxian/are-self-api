import asyncio
import os
import sys
import time

import pytest

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from talos_agent.talos_agent import AsyncLogMonitor


@pytest.mark.asyncio
async def test_log_monitor_basic(tmp_path):
    log_file = tmp_path / 'test.log'
    log_file.write_text('line 1\n', encoding='utf-8')

    # We use a launch_time in the past to ensure it picks up existing lines
    monitor = AsyncLogMonitor(str(log_file), launch_time=time.time() - 100)
    await monitor.start()

    # Wait for watchfiles to pick it up (can be slow)
    # 50 iterations * 0.1s = 5 seconds tolerance
    for _ in range(50):
        lines = await monitor.check_for_lines()
        if 'line 1\n' in lines:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail('Log monitor did not pick up first line (Timeout 5s)')

    # Add another line
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write('line 2\n')
        f.flush()
        os.fsync(f.fileno())

    for _ in range(50):
        lines = await monitor.check_for_lines()
        if 'line 2\n' in lines:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail('Log monitor did not pick up second line (Timeout 5s)')

    await monitor.stop()


@pytest.mark.asyncio
async def test_log_monitor_patience(tmp_path):
    # Test that it waits for file to appear
    log_file = tmp_path / 'late.log'
    monitor = AsyncLogMonitor(str(log_file), launch_time=time.time())

    start_task = asyncio.create_task(monitor.start())

    # Wait a bit, then create the file
    await asyncio.sleep(0.5)
    log_file.write_text('finally here\n', encoding='utf-8')

    for _ in range(50):
        lines = await monitor.check_for_lines()
        if 'finally here\n' in lines:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail(
            'Log monitor did not pick up late-appearing file (Timeout 5s)'
        )

    await monitor.stop()
    await start_task


@pytest.mark.asyncio
async def test_log_monitor_rotation(tmp_path):
    log_file = tmp_path / 'rotated.log'
    log_file.write_text('old line 1\n', encoding='utf-8')

    monitor = AsyncLogMonitor(str(log_file), launch_time=time.time() - 100)
    await monitor.start()

    # Clear initial lines (wait for catch-up)
    for _ in range(50):
        lines = await monitor.check_for_lines()
        if lines:
            break
        await asyncio.sleep(0.1)

    # Simulate rotation: truncate and write new stuff
    log_file.write_text('rotated\n', encoding='utf-8')

    for _ in range(50):
        lines = await monitor.check_for_lines()
        if 'rotated\n' in lines:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail(
            'Log monitor did not handle rotation/truncation (Timeout 5s)'
        )

    await monitor.stop()
