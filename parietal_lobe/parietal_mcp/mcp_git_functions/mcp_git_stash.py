import asyncio
import subprocess

from django.conf import settings


def _stash_sync(
    action: str = 'push',
    message: str = None,
    repo_path: str = None,
) -> str:
    """Manages the git stash."""
    cwd = repo_path or str(getattr(settings, 'BASE_DIR', 'c:/talos'))

    STASH_ACTIONS = frozenset({'push', 'pop', 'list', 'drop'})
    action = action.lower()

    if action not in STASH_ACTIONS:
        return (
            f"Error: Invalid stash action '{action}'. "
            f"Must be one of: {', '.join(sorted(STASH_ACTIONS))}."
        )

    cmd = ['git', 'stash', action]
    if action == 'push' and message:
        cmd.extend(['-m', message])

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            return f'Error: git stash {action} failed: {result.stderr.strip()}'

        output = result.stdout.strip()
        return output if output else f'Success: stash {action} completed.'

    except subprocess.TimeoutExpired:
        return f'Error: git stash {action} timed out.'
    except FileNotFoundError:
        return 'Error: git executable not found.'
    except Exception as e:
        return f'Error running git stash: {str(e)}'


async def execute(
    action: str = 'push',
    message: str = None,
    repo_path: str = None,
) -> str:
    """Manages the git stash (push, pop, list, drop)."""
    return await asyncio.to_thread(_stash_sync, action, message, repo_path)
