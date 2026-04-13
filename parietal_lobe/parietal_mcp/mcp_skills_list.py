"""MCP Tool: List available skills with optional category filter."""
from typing import Any, Dict

from asgiref.sync import sync_to_async

from parietal_lobe.parietal_mcp.mcp_skills_list_sync import run_skills_list


async def mcp_skills_list(
    category: str = '',
) -> Dict[str, Any]:
    """List available skills. Optionally filter by category."""
    return await sync_to_async(run_skills_list)(category)
