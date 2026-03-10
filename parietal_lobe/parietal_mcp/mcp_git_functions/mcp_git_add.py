import asyncio
import subprocess

from django.conf import settings


def _add_sync(
    file_path: str = None,
    all_files: bool = False,
    repo_path: str = None,
) -> str:
    """Stages files for commit."""
    cwd = repo_path or str(getattr(settings, 'BASE_DIR', 'c:/talos'))

    if not file_path and not all_files:
        return (
            'Error: Specify file_path to stage a specific file, '
            'or set all_files=True to stage everything.'
        )

    cmd = ['git', 'add']
    if all_files:
        cmd.append('-A')
    else:
        cmd.append(file_path)

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            return f'Error: git add failed: {result.stderr.strip()}'

        target = 'all files' if all_files else file_path
        return f'Success: Staged {target}.'

    except subprocess.TimeoutExpired:
        return 'Error: git add timed out.'
    except FileNotFoundError:
        return 'Error: git executable not found.'
    except Exception as e:
        return f'Error running git add: {str(e)}'


async def execute(
    file_path: str = None,
    all_files: bool = False,
    repo_path: str = None,
) -> str:
    """Stages files for the next commit."""
    return await asyncio.to_thread(
        _add_sync, file_path, all_files, repo_path
    )
