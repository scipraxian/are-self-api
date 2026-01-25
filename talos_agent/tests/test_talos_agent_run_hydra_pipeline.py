import asyncio
import os
import sys

import pytest

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from talos_agent.talos_agent import run_hydra_pipeline


@pytest.mark.asyncio
async def test_run_hydra_pipeline_basic(tmp_path):
    log_file = tmp_path / "pipeline.log"

    if sys.platform == 'win32':
        # Use ping for a small delay
        cmd = [
            'cmd', '/c',
            f'echo process_out && ping 127.0.0.1 -n 2 > nul && echo log_out > "{log_file}"'
        ]
    else:
        cmd = [
            'sh', '-c',
            f'echo process_out; sleep 1; echo log_out > "{log_file}"'
        ]

    captured_output = []

    async def callback(text):
        captured_output.append(text.strip())

    exit_code = await run_hydra_pipeline(cmd, str(log_file), callback)

    # Debug checks
    file_exists = os.path.exists(log_file)
    content = ""
    if file_exists:
        with open(log_file, 'r') as f:
            content = f.read()

    if exit_code != 0 or "process_out" not in captured_output or "log_out" not in captured_output:
        print(f"DEBUG: exit_code={exit_code}")
        print(f"DEBUG: captured={captured_output}")
        print(f"DEBUG: file_exists={file_exists}")
        print(f"DEBUG: file_content={content!r}")

    assert exit_code == 0
    assert "process_out" in captured_output
    assert "log_out" in captured_output


@pytest.mark.asyncio
async def test_run_hydra_pipeline_no_log():
    if sys.platform == 'win32':
        cmd = ['cmd', '/c', 'echo only_process']
    else:
        cmd = ['echo', 'only_process']

    captured_output = []

    async def callback(text):
        captured_output.append(text.strip())

    exit_code = await run_hydra_pipeline(cmd, None, callback)

    assert exit_code == 0
    assert any("only_process" in line for line in captured_output)
