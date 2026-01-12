import re
import json


def parse_ai_actions(text):
    """
    Extracts action blocks. Supports:
    1. JSON: :::ACTION {"tool": "x", "args": {...}} :::
    2. Drifted JSON: :::ai_read_file {"path": "x"} :::
    3. Function Call: :::ai_read_file(path="x") :::
    """
    pattern = r":::(\w+)?\s*(.*?)\s*:::"
    matches = re.findall(pattern, text, re.DOTALL)

    actions = []
    for tag, content in matches:
        tag = tag.strip() if tag else ""
        content = content.strip()

        if content.startswith('(') and content.endswith(')'):
            content = content[1:-1]

        try:
            payload = json.loads(content.strip())
            if tag.upper() == 'ACTION' or not tag:
                if 'tool' in payload:
                    actions.append(payload)
            else:
                actions.append({'tool': tag, 'args': payload})
            continue
        except json.JSONDecodeError:
            pass

        if tag and tag.upper() != 'ACTION':
            args = {}
            arg_pattern = r'(\w+)=[\'"](.*?)[\'"]'
            arg_matches = re.findall(arg_pattern, content)

            for key, val in arg_matches:
                args[key] = val

            if args:
                actions.append({'tool': tag, 'args': args})

    return actions