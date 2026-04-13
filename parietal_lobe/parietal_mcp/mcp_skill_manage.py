"""MCP Tool: Manage skills (create, patch, edit, delete, write_file, remove_file)."""
from typing import Any, Dict

from asgiref.sync import sync_to_async

from parietal_lobe.parietal_mcp.mcp_skill_manage_sync import run_skill_manage


async def mcp_skill_manage(
    action: str,
    name: str = '',
    content: str = '',
    old_text: str = '',
    new_text: str = '',
    replace_all: bool = False,
    file_path: str = '',
    file_content: str = '',
    category: str = '',
) -> Dict[str, Any]:
    """Manage skills: create, patch, edit, delete, write_file, remove_file."""
    return await sync_to_async(run_skill_manage)(
        action,
        name,
        content,
        old_text,
        new_text,
        replace_all,
        file_path,
        file_content,
        category,
    )
