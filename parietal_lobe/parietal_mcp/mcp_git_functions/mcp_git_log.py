import asyncio
import subprocess

from django.conf import settings

MAX_LOG_ENTRIES = 20
MAX_LOG_CHARS = 15000


def _log_sync(
    repo_path: str = None,
    count: int = MAX_LOG_ENTRIES,
    file_path: str = None,
    oneline: bool = True,
) -> str:
    """Runs git log and returns formatted output."""
    cwd = repo_path or str(settings.BASE_DIR)

    safe_count = max(1, min(count, MAX_LOG_ENTRIES))

    cmd = ['git', 'log', f'-{safe_count}']
    if oneline:
        cmd.append('--oneline')
    else:
        cmd.extend([
            '--format=%H%n%an <%ae>%n%ai%n%s%n%b%n---',
        ])

    if file_path:
        cmd.extend(['--', file_path])

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            return f'Error: git log failed: {result.stderr.strip()}'

        output = result.stdout.strip()
        if not output:
            return 'No commits found.'

        if len(output) > MAX_LOG_CHARS:
            output = output[:MAX_LOG_CHARS]
            output += '\n\n... [Log truncated]'

        return output

    except subprocess.TimeoutExpired:
        return 'Error: git log timed out.'
    except FileNotFoundError:
        return 'Error: git executable not found.'
    except Exception as e:
        return f'Error running git log: {str(e)}'


async def execute(
    repo_path: str = None,
    count: int = MAX_LOG_ENTRIES,
    file_path: str = None,
    oneline: bool = True,
) -> str:
    """Shows recent commit history."""
    return await asyncio.to_thread(
        _log_sync, repo_path, count, file_path, oneline
    )
