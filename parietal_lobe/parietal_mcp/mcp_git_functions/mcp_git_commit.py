import asyncio
import subprocess

from django.conf import settings


def _commit_sync(message: str, repo_path: str = None) -> str:
    """Runs git commit with the given message."""
    cwd = repo_path or str(getattr(settings, 'BASE_DIR', 'c:/talos'))

    if not message or not message.strip():
        return 'Error: Commit message is required.'

    try:
        result = subprocess.run(
            ['git', 'commit', '-m', message],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if 'nothing to commit' in stderr.lower():
                return 'Nothing to commit. Stage changes first with add.'
            return f'Error: git commit failed: {stderr}'

        return result.stdout.strip()

    except subprocess.TimeoutExpired:
        return 'Error: git commit timed out.'
    except FileNotFoundError:
        return 'Error: git executable not found.'
    except Exception as e:
        return f'Error running git commit: {str(e)}'


async def execute(message: str, repo_path: str = None) -> str:
    """Commits staged changes with the given message."""
    return await asyncio.to_thread(_commit_sync, message, repo_path)
