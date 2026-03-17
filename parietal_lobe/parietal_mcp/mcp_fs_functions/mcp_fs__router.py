import importlib
import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)

MODULE_PREFIX = 'parietal_lobe.parietal_mcp.mcp_fs_functions.mcp_fs_'

ALLOWED_ACTIONS = frozenset(
    {
        'read',
        'list',
        'grep',
        'patch',
    }
)

WRITE_ACTIONS = frozenset(
    {
        'patch',
    }
)

BLOCKED_PATH_SEGMENTS = frozenset(
    {
        'venv',
        '__pycache__',
        '.git',
        'node_modules',
        'site-packages',
    }
)


def _get_base_dir() -> str:
    return os.path.normpath(str(getattr(settings, 'BASE_DIR', '/')))


def _validate_action(action: str) -> str | None:
    """Returns an error string if the action is invalid, else None."""
    if action not in ALLOWED_ACTIONS:
        return (
            f"Error: Invalid action '{action}'. "
            f'Must be one of: {", ".join(sorted(ALLOWED_ACTIONS))}.'
        )
    return None


def _validate_path_safety(path: str, action: str) -> str | None:
    """Returns an error string if the path is unsafe, else None."""
    if not path:
        return 'Error: path is required.'

    normalized = os.path.normpath(path).replace('\\', '/')
    segments = normalized.split('/')

    for segment in segments:
        if segment in BLOCKED_PATH_SEGMENTS:
            return (
                f'Error: Access denied. Path contains '
                f"blocked segment '{segment}'."
            )

    if action in WRITE_ACTIONS and not os.path.isabs(path):
        base_dir = _get_base_dir()
        full_path = os.path.normpath(os.path.join(base_dir, path))

        try:
            common = os.path.commonpath([base_dir, full_path])
            if common.lower() != base_dir.lower():
                return (
                    'Error: Write access denied. '
                    'Target is outside the project root.'
                )
        except ValueError:
            return 'Error: Write access denied. Drive mismatch.'

    return None


async def route(action: str, params: dict) -> str:
    """
    Central routing and policy engine for filesystem operations.

    1. Validates the action against ALLOWED_ACTIONS.
    2. Enforces path safety guardrails.
    3. Dispatches to the appropriate functional module.
    """
    action = str(action).lower()

    action_error = _validate_action(action)
    if action_error:
        return action_error

    path = params.get('path', '')
    if path:
        path_error = _validate_path_safety(path, action)
        if path_error:
            return path_error

    module_path = f'{MODULE_PREFIX}{action}'

    try:
        module = importlib.import_module(module_path)
    except ImportError:
        logger.error(f'[mcp_fs_router] Module not found: {module_path}')
        return f"Error: Action '{action}' module not found."

    execute_fn = getattr(module, 'execute', None)
    if not execute_fn:
        logger.error(f'[mcp_fs_router] No execute() in {module_path}')
        return f"Error: Action '{action}' has no execute function."

    try:
        return await execute_fn(**params)
    except TypeError as e:
        return f'Error: Invalid parameters for action {action}: {str(e)}'
    except Exception as e:
        logger.exception(f'[mcp_fs_router] Execution crash in {action}')
        return f'Error: {action} execution failed: {str(e)}'
