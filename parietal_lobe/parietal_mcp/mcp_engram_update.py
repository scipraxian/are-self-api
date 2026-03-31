from hippocampus.hippocampus import TalosHippocampus


async def mcp_engram_update(
    session_id: str, engram_id: str, additional_fact: str, turn_id: int,
    thought: str = ''
) -> str:
    """MCP Tool: Appends new findings to an existing Engram. REQUIRES THE ENGRAM ID."""
    return await TalosHippocampus.update_engram(
        session_id, engram_id, additional_fact, turn_id
    )
