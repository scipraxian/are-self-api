"""
Structured memory entries as Hippocampus Engrams (agent_memory / user_profile).
"""
from typing import Any, Dict

from asgiref.sync import sync_to_async

from parietal_lobe.parietal_mcp.mcp_memory_sync import run_memory_action


async def mcp_memory(
    action: str,
    collection: str,
    session_id: str = '',
    turn_id: str = '',
    content: str = '',
    old_content: str = '',
    new_content: str = '',
    content_snippet: str = '',
) -> Dict[str, Any]:
    """Add, replace, or remove a tagged memory entry."""
    return await sync_to_async(run_memory_action)(
        action,
        collection,
        content,
        old_content,
        new_content,
        content_snippet,
        session_id,
        turn_id,
    )
