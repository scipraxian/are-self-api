import asyncio
import sys

import pytest

from talos_agent.talos_agent import run_hydra_pipeline

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@pytest.mark.asyncio
async def test_run_hydra_pipeline_basic(tmp_path):
    # Use python itself to guarantee cross-platform behavior without shell syntax quirks
    script = "import time; print('start', flush=True); time.sleep(0.5); print('end', flush=True)"
    cmd = [sys.executable, '-c', script]

    captured = []

    async def callback(text):
        captured.append(text.strip())

    exit_code = await run_hydra_pipeline(cmd, None, callback)

    assert exit_code == 0
    assert 'start' in captured
    assert 'end' in captured


# @pytest.mark.asyncio
# async def test_run_hydra_pipeline_leash_broken():
#     """
#     CRITICAL: Verify that if the callback raises a Network Error,
#     the process is killed and the exception bubbles up IMMEDIATELY.
#     """
#     # 1. Force IMMEDIATE, CONSTANT output to trigger the callback loop
#     script = "import time; \nwhile True: print('data', flush=True); time.sleep(0.1)"
#     cmd = [sys.executable, '-c', script]
#
#     # 2. A callback that crashes immediately to simulate broken pipe
#     async def broken_callback(text):
#         raise ConnectionResetError('Simulated Network Drop')
#
#     # 3. The pipeline should raise the error, NOT hang
#     with pytest.raises(ConnectionResetError):
#         # Timeout ensures we don't hang if the kill logic fails
#         await asyncio.wait_for(
#             run_hydra_pipeline(cmd, None, broken_callback),
#             timeout=5.0
#         )
