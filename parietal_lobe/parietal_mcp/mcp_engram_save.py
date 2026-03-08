from hippocampus.hippocampus import TalosHippocampus


async def mcp_engram_save(
    session_id: str,
    title: str,
    fact: str,
    turn_id: int,
    tags: str = '',
    relevance: float = 1.0,
) -> str:
    """MCP Tool: Crystallizes a NEW fact into an Engram card."""
    return await TalosHippocampus.save_engram(session_id, title, fact, turn_id,
                                              tags, relevance)
