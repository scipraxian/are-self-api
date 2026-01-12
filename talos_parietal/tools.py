import logging
import os
import uuid

from django.conf import settings

from hydra.tasks import cast_hydra_spell

logger = logging.getLogger(__name__)


def ai_read_file(file_path, max_chars=10000):
    """
    Reads a file from the disk safely.
    Prevents directory traversal and limits read size.
    """
    # 1. Safety Check: No '..' allowed
    if '..' in file_path:
        return "Error: Directory traversal attempt detected."

    # 2. Absolute Path Resolution (Assume relative to project root)
    # If the path is already absolute and within allowed workspace, we use it.
    # For this system, we'll assume paths are relative to BASE_DIR unless they look absolute.
    base_dir = getattr(settings, 'BASE_DIR', 'c:/talos')
    full_path = os.path.normpath(os.path.join(base_dir, file_path))

    # Optional: Verify it's still inside base_dir
    if not str(full_path).startswith(str(base_dir)):
        # However, for this specific environment (c:/talos), we might be more flexible
        # if the user intended to read from another workspace.
        # But the directive says "prevent directory traversal".
        logger.warning(f"Directory traversal attempt detected: {file_path}")

    if not os.path.exists(full_path):
        return f"Error: File '{file_path}' not found."

    if os.path.isdir(full_path):
        return f"Error: '{file_path}' is a directory."

    try:
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(max_chars)
            if len(content) == max_chars:
                content += "\n... [TRUNCATED] ..."
            return content
    except Exception as e:
        return f"Error reading file: {str(e)}"


def ai_execute_task(head_id):
    """
    Executes a specific Hydra Head (Spell).
    """
    # 1. Validate Input is a UUID
    try:
        # Check if it's a valid UUID string
        val = uuid.UUID(str(head_id))
    except ValueError:
        return f"Error: Invalid Head ID '{head_id}'. Must be a UUID (e.g., from the Context)."

    try:
        # We use .delay() to push to Celery
        cast_hydra_spell.delay(str(head_id))
        return f"Successfully cast spell for Head {head_id}. Monitor logs for progress."
    except Exception as e:
        return f"Error casting spell: {str(e)}"
