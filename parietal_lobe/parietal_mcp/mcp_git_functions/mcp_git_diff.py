import asyncio
import subprocess

from django.conf import settings

MAX_DIFF_CHARS = 20000


def _diff_sync(
    repo_path: str = None,
    staged: bool = False,
    file_path: str = None,
) -> str:
    """Runs git diff and returns the output."""
    cwd = repo_path or str(settings.BASE_DIR)

    cmd = ['git', 'diff']
    if staged:
        cmd.append('--cached')
    if file_path:
        cmd.extend(['--', file_path])

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return f'Error: git diff failed: {result.stderr.strip()}'

        output = result.stdout.strip()
        if not output:
            scope = 'staged' if staged else 'working tree'
            return f'No differences in {scope}.'

        if len(output) > MAX_DIFF_CHARS:
            output = output[:MAX_DIFF_CHARS]
            output += '\n\n... [Diff truncated due to length]'

        return output

    except subprocess.TimeoutExpired:
        return 'Error: git diff timed out.'
    except FileNotFoundError:
        return 'Error: git executable not found.'
    except Exception as e:
        return f'Error running git diff: {str(e)}'


async def execute(
    repo_path: str = None,
    staged: bool = False,
    file_path: str = None,
) -> str:
    """Shows diff of working tree or staged changes."""
    return await asyncio.to_thread(_diff_sync, repo_path, staged, file_path)
