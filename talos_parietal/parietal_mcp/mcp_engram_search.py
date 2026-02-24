from talos_hippocampus.talos_hippocampus import TalosHippocampus


async def mcp_engram_search(query: str = '', tags: str = '') -> str:
    """MCP Tool: Searches the permanent Hippocampus catalog. Returns Titles only."""
    return await TalosHippocampus.search_engrams(query=query, tags=tags)
