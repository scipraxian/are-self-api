from typing import Any, Dict, List

from frontal_lobe.models import ReasoningTurn


def your_move_addon(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    content = (
        'YOUR MOVE:\n'
        '1. You MUST call mcp_internal_monologue ALONGSIDE any other tools you call in parallel. Never fire a tool without also firing your monologue.\n'
        '2. You should call your tools (like `mcp_ticket`) in parallel during the exact same turn.\n'
        '3. Use structured JSON for all tool calls natively.\n'
    )
    return [{"role": "user", "content": content}]
