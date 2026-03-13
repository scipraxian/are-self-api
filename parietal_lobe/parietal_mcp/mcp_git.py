from parietal_lobe.parietal_mcp.mcp_git_functions.mcp_git__router import route


async def mcp_git(action: str, params: dict) -> str:
    """MCP Tool: Unified git operations.

    Actions: status, diff, log, commit, add, stash, branch, checkout.
    Pass 'action' to select the operation and 'params' as a dict of arguments.

    Examples:
        action='status',   params={}
        action='diff',     params={'staged': True}
        action='log',      params={'count': 10, 'oneline': True}
        action='add',      params={'file_path': 'foo.py'}
        action='commit',   params={'message': 'Fix bug in parser'}
        action='stash',    params={'action': 'push', 'message': 'WIP'}
        action='branch',   params={'branch_name': 'feature-x', 'create': True}
        action='checkout', params={'target': 'main'}
    """
    return await route(action, params)
