from hippocampus.hippocampus import Hippocampus


async def mcp_engram_search(
    query: str = '', tags: str = '', thought: str = ''
) -> str:
    """MCP Tool: Searches the permanent Hippocampus catalog. Returns Titles only."""
    return await Hippocampus.search_engrams(query=query, tags=tags)
