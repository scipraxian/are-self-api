import re
import json


def parse_ai_actions(text):
    """
    Extracts action blocks. Supports:
    1. JSON: :::ACTION {"tool": "x", "args": {...}} :::
    2. Drifted JSON: :::ai_read_file {"path": "x"} :::
    3. Function Call: :::ai_read_file(path="x") :::
    4. Lazy Ending: :::tool(...) (Missing closing colons)
    """
    # Regex Update:
    # (?:::|$) means "Match ':::' OR the end of the string"
    pattern = r":::(\w+)?\s*(.*?)(?:::|$)"
    matches = re.findall(pattern, text, re.DOTALL)

    actions = []
    for tag, content in matches:
        tag = tag.strip() if tag else ""
        content = content.strip()

        # Cleanup wrapping parens
        if content.startswith('(') and content.endswith(')'):
            content = content[1:-1]

        # STRATEGY A: JSON
        try:
            payload = json.loads(content)
            if tag.upper() == 'ACTION' or not tag:
                if 'tool' in payload:
                    actions.append(payload)
            else:
                actions.append({'tool': tag, 'args': payload})
            continue
        except json.JSONDecodeError:
            pass

        # STRATEGY B: Pythonic Args (key="value")
        if tag and tag.upper() != 'ACTION':
            args = {}
            # Handles path="C:\..." (Quoted) and numbers (Unquoted)
            arg_pattern = r'(\w+)=[\'"](.*?)[\'"]|(\w+)=(\d+)'
            arg_matches = re.findall(arg_pattern, content)

            for key_str, val_str, key_int, val_int in arg_matches:
                if key_str:
                    args[key_str] = val_str
                elif key_int:
                    args[key_int] = int(val_int)

            if args:
                actions.append({'tool': tag, 'args': args})

    return actions