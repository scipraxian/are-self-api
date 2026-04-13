"""MCP Tool: View a skill's content and attached files."""
from typing import Any, Dict

from asgiref.sync import sync_to_async

from parietal_lobe.parietal_mcp.mcp_skill_view_sync import run_skill_view


async def mcp_skill_view(
    name: str,
    file_path: str = '',
) -> Dict[str, Any]:
    """View a skill's SKILL.md content and attached files."""
    return await sync_to_async(run_skill_view)(name, file_path)
