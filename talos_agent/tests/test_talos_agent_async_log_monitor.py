import asyncio
import sys
import time

import pytest

from talos_agent.talos_agent import AsyncLogMonitor, TalosAgentConstants

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


async def consume_stream(monitor, timeout=2.0):
    """Helper to collect items from the monitor stream with a timeout."""
    collected = []

    async def _reader():
        async for line in monitor.stream_changes():
            collected.append(line)

    # Run the reader in the background so we can stop it later
    task = asyncio.create_task(_reader())

    try:
        # Allow it to run for 'timeout' seconds
        await asyncio.sleep(timeout)
    finally:
        # Crucial: We must call stop() to break the _reader loop!
        await monitor.stop()
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass

    return collected


@pytest.mark.asyncio
async def test_log_monitor_basic(tmp_path):
    log_file = tmp_path / 'test.log'
    log_file.write_text('line 1\n', encoding='utf-8')

    monitor = AsyncLogMonitor(str(log_file), launch_time=time.time() - 100)

    lines = await consume_stream(monitor, timeout=2.0)

    assert 'line 1\n' in lines


@pytest.mark.asyncio
async def test_log_monitor_live_updates(tmp_path):
    log_file = tmp_path / 'live.log'
    log_file.touch()

    monitor = AsyncLogMonitor(str(log_file), launch_time=time.time())

    collected = []

    # 1. Writer Task (Simulates the app writing logs)
    async def _writer():
        await asyncio.sleep(0.5)
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write('update 1\n')
            f.flush()
        await asyncio.sleep(0.5)
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write('update 2\n')
            f.flush()

    # 2. Reader Task (Consumes the stream)
    async def _reader():
        async for line in monitor.stream_changes():
            collected.append(line)

    writer_task = asyncio.create_task(_writer())
    reader_task = asyncio.create_task(_reader())

    # Wait for writer to finish
    await writer_task

    # Give the reader a moment to catch the last write
    await asyncio.sleep(0.5)

    # 3. Stop everything
    await monitor.stop()
    await reader_task

    assert 'update 1\n' in collected
    assert 'update 2\n' in collected


@pytest.mark.asyncio
async def test_log_monitor_patience(tmp_path):
    """Test waiting for a file that doesn't exist yet."""
    log_file = tmp_path / 'late.log'
    monitor = AsyncLogMonitor(str(log_file), launch_time=time.time())

    collected = []

    async def _reader():
        async for line in monitor.stream_changes():
            collected.append(line)

    reader_task = asyncio.create_task(_reader())

    # Wait 1s, then create file
    await asyncio.sleep(1.0)
    log_file.write_text('I have arrived\n', encoding='utf-8')

    # Give it time to pick up
    await asyncio.sleep(1.0)

    await monitor.stop()
    await reader_task

    assert 'I have arrived\n' in collected


@pytest.mark.asyncio
async def test_log_monitor_never_appears(tmp_path):
    """Test that it reports failure if file never shows up."""
    # 1. Reduce timeout for test speed (temporarily modify constant)
    original_timeout = TalosAgentConstants.TIMEOUT_LOG_APPEAR
    TalosAgentConstants.TIMEOUT_LOG_APPEAR = 1.0

    log_file = tmp_path / 'ghost.log'
    monitor = AsyncLogMonitor(str(log_file), launch_time=time.time())

    collected = []

    # 2. Start a "Stopper" task
    # This ensures we break the loop even if the file never appears
    async def _stop_later():
        await asyncio.sleep(1.5)  # Wait slightly longer than the timeout
        await monitor.stop()

    stopper = asyncio.create_task(_stop_later())

    # 3. Run the blocking loop (now safe because stopper will kill it)
    async for line in monitor.stream_changes():
        collected.append(line)

    # Restore constant
    TalosAgentConstants.TIMEOUT_LOG_APPEAR = original_timeout
    await stopper

    # Should contain the error message
    assert any('never appeared' in line for line in collected)
