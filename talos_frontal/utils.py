import re
import json
import ast
import logging

logger = logging.getLogger(__name__)


def parse_ai_actions(text):
    """
    Extracts action blocks. Hybrid approach supporting:
    1. JSON: :::ACTION {"tool": "x"} :::
    2. Drifted JSON: :::ai_read_file {"path": "x"} :::
    3. Pythonic: :::ai_read_file(path="x") :::
    4. Positional: :::ai_list_files('.') :::
    """
    # Regex Update:
    # 1. (\w+)? -> Optional Tag (e.g. "ACTION" or "ai_read_file")
    # 2. \s* -> Whitespace
    # 3. (.*?) -> Content (lazy match)
    # 4. (?:::|$) -> End at next ::: OR End of String
    # Note: We rely on the loop to refine the content parsing.
    # Regex Update: Allow spaces after :::
    # Old: r":::(\w+)?\s*(.*?)(?:::|$)"
    # New: r":::\s*(\w+)?\s*(.*?)(?:::|$)"
    pattern = r":::\s*(\w+)?\s*(.*?)(?:::|$)"
    matches = re.findall(pattern, text, re.DOTALL)

    actions = []

    # Map for positional args -> keyword args (AST Logic)
    arg_map = {
        'ai_read_file': ['path', 'start_line', 'max_lines'],
        'ai_search_file': ['path', 'pattern'],
        'ai_list_files': ['path'],
        'ai_execute_task': ['head_id'],
    }

    for tag, content in matches:
        tag = tag.strip() if tag else ""
        content = content.strip()

        if not content:
            continue

        # --- STRATEGY A: JSON (Legacy & Drifted) ---
        # If it looks like a dict/object
        if content.startswith('{'):
            try:
                payload = json.loads(content)
                if tag.upper() == 'ACTION' or not tag:
                    if 'tool' in payload:
                        actions.append(payload)
                else:
                    # Tag is the tool name (Drifted)
                    actions.append({'tool': tag, 'args': payload})
                continue
            except json.JSONDecodeError:
                pass

        # --- STRATEGY B: AST (Pythonic) ---
        # If it looks like a function call args: (...)
        if content.startswith('('):
            try:
                # Wrap in fake call
                tree = ast.parse(f"call{content}")
                call = tree.body[0].value

                kwargs = {k.arg: ast.literal_eval(k.value) for k in call.keywords}

                # Positional Mapping
                tool_name = tag
                if call.args:
                    mapping = arg_map.get(tool_name, [])
                    for i, arg_val in enumerate(call.args):
                        if i < len(mapping):
                            key = mapping[i]
                            if key not in kwargs:
                                kwargs[key] = ast.literal_eval(arg_val)

                if tool_name:
                    actions.append({'tool': tool_name, 'args': kwargs})
                continue
            except Exception:
                pass

        # --- STRATEGY C: REGEX FALLBACK (Desperation) ---
        # Handles: :::ai_read_file path="foo" ::: (No parens, no braces)
        if tag and tag.upper() != 'ACTION':
            args = {}
            # Capture key="val" OR key='val' OR key=123
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