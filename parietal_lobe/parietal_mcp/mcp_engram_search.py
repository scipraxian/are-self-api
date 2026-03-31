from hippocampus.hippocampus import TalosHippocampus


async def mcp_engram_search(
    query: str = '', tags: str = '', thought: str = ''
) -> str:
    """MCP Tool: Searches the permanent Hippocampus catalog. Returns Titles only."""
    return await TalosHippocampus.search_engrams(query=query, tags=tags)
