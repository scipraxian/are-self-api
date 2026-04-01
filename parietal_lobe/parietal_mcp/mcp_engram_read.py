from hippocampus.hippocampus import Hippocampus


async def mcp_engram_read(
    session_id: str, engram_id: int, thought: str = ''
) -> str:
    """MCP Tool: Reads the full fact of a specific Engram by ID."""
    return await Hippocampus.read_engram(session_id, engram_id)
