import importlib
import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)

MODULE_PREFIX = 'parietal_lobe.parietal_mcp.mcp_git_functions.mcp_git_'

ALLOWED_ACTIONS = frozenset({
    'status',
    'diff',
    'log',
    'commit',
    'add',
    'stash',
    'branch',
    'checkout',
})

MUTATING_ACTIONS = frozenset({
    'commit',
    'add',
    'stash',
    'checkout',
})


def _validate_action(action: str) -> str | None:
    """Returns an error string if the action is invalid, else None."""
    if action not in ALLOWED_ACTIONS:
        return (
            f"Error: Invalid git action '{action}'. "
            f"Must be one of: {', '.join(sorted(ALLOWED_ACTIONS))}."
        )
    return None


def _validate_repo_path(repo_path: str) -> str | None:
    """Returns an error string if the repo_path is unsafe, else None."""
    if not repo_path:
        return None

    normalized = os.path.normpath(repo_path)
    if not os.path.isdir(normalized):
        return f"Error: Repository path '{repo_path}' is not a directory."

    git_dir = os.path.join(normalized, '.git')
    if not os.path.isdir(git_dir):
        return f"Error: '{repo_path}' is not a git repository."

    return None


async def route(action: str, params: dict) -> str:
    """
    Central routing and policy engine for git operations.

    1. Validates the action against ALLOWED_ACTIONS.
    2. Validates repo_path if provided.
    3. Dispatches to the appropriate functional module.
    """
    action = str(action).lower()

    action_error = _validate_action(action)
    if action_error:
        return action_error

    repo_path = params.get('repo_path')
    if repo_path:
        repo_error = _validate_repo_path(repo_path)
        if repo_error:
            return repo_error

    module_path = f'{MODULE_PREFIX}{action}'

    try:
        module = importlib.import_module(module_path)
    except ImportError:
        logger.error(
            f'[mcp_git_router] Module not found: {module_path}'
        )
        return f"Error: Git action '{action}' module not found."

    execute_fn = getattr(module, 'execute', None)
    if not execute_fn:
        logger.error(
            f'[mcp_git_router] No execute() in {module_path}'
        )
        return f"Error: Git action '{action}' has no execute function."

    try:
        return await execute_fn(**params)
    except TypeError as e:
        return f'Error: Invalid parameters for git {action}: {str(e)}'
    except Exception as e:
        logger.exception(
            f'[mcp_git_router] Execution crash in {action}'
        )
        return f'Error: git {action} execution failed: {str(e)}'
