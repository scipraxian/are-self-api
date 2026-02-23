from talos_hippocampus.talos_hippocampus import TalosHippocampus


async def mcp_engram_update(session_id: str, title: str,
                            additional_fact: str) -> str:
    """MCP Tool: Appends new findings to an existing Engram."""
    return await TalosHippocampus.update_engram(session_id, title,
                                                additional_fact)
