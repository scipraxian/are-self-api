import asyncio
import subprocess

from django.conf import settings


def _checkout_sync(target: str, repo_path: str = None) -> str:
    """Switches branches or restores working tree files."""
    cwd = repo_path or str(getattr(settings, 'BASE_DIR', 'c:/talos'))

    if not target:
        return 'Error: target (branch name or file path) is required.'

    cmd = ['git', 'checkout', target]

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            return f'Error: git checkout failed: {result.stderr.strip()}'

        output = result.stdout.strip() or result.stderr.strip()
        return output if output else f'Success: Checked out {target}.'

    except subprocess.TimeoutExpired:
        return 'Error: git checkout timed out.'
    except FileNotFoundError:
        return 'Error: git executable not found.'
    except Exception as e:
        return f'Error running git checkout: {str(e)}'


async def execute(target: str, repo_path: str = None) -> str:
    """Switches to a branch or restores a file."""
    return await asyncio.to_thread(_checkout_sync, target, repo_path)
