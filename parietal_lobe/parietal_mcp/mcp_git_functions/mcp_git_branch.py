import asyncio
import subprocess

from django.conf import settings


def _branch_sync(
    branch_name: str = None,
    create: bool = False,
    delete: bool = False,
    repo_path: str = None,
) -> str:
    """Manages git branches."""
    cwd = repo_path or str(settings.BASE_DIR)

    if delete and branch_name:
        cmd = ['git', 'branch', '-d', branch_name]
    elif create and branch_name:
        cmd = ['git', 'branch', branch_name]
    elif branch_name is None:
        cmd = ['git', 'branch', '-a']
    else:
        return 'Error: Provide branch_name with create or delete flag.'

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            return f'Error: git branch failed: {result.stderr.strip()}'

        output = result.stdout.strip()
        return output if output else 'Success: Branch operation completed.'

    except subprocess.TimeoutExpired:
        return 'Error: git branch timed out.'
    except FileNotFoundError:
        return 'Error: git executable not found.'
    except Exception as e:
        return f'Error running git branch: {str(e)}'


async def execute(
    branch_name: str = None,
    create: bool = False,
    delete: bool = False,
    repo_path: str = None,
) -> str:
    """Lists, creates, or deletes branches."""
    return await asyncio.to_thread(
        _branch_sync, branch_name, create, delete, repo_path
    )
