import asyncio
import subprocess

from django.conf import settings


def _status_sync(repo_path: str = None) -> str:
    """Runs git status and returns the output."""
    cwd = repo_path or str(getattr(settings, 'BASE_DIR', 'c:/talos'))

    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain', '-b'],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
        )

        output = result.stdout.strip()
        if result.returncode != 0:
            return f'Error: git status failed: {result.stderr.strip()}'

        if not output:
            return 'Working tree clean. Nothing to commit.'

        return output

    except subprocess.TimeoutExpired:
        return 'Error: git status timed out.'
    except FileNotFoundError:
        return 'Error: git executable not found.'
    except Exception as e:
        return f'Error running git status: {str(e)}'


async def execute(repo_path: str = None) -> str:
    """Returns the current git status in porcelain format."""
    return await asyncio.to_thread(_status_sync, repo_path)
