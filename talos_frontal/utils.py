import re
import json
import logging
import ast

logger = logging.getLogger(__name__)


def parse_ai_actions(text):
    """
    EXTREMELY ROBUST PARSER (Level 200).
    Extracts action blocks from AI thought streams.

    Strategies:
    1. Tagged Blocks: :::tool(...) :::
    2. JSON Blocks: :::ACTION {...} :::
    3. NAKED CALLS: ai_read_file(...) (Fallback if tags missing)
    """
    actions = []

    # --- STRATEGY 1 & 2: TAGGED BLOCKS (High Confidence) ---
    pattern_tagged = r":::\s*(\w+)?\s*(.*?)(?:::|$)"
    matches_tagged = list(re.finditer(pattern_tagged, text, re.DOTALL))

    for match in matches_tagged:
        tag = (match.group(1) or "").strip()
        content = match.group(2).strip()

        if not content: continue

        # JSON Try
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                if tag.upper() == 'ACTION' or not tag:
                    if 'tool' in data: actions.append(data)
                else:
                    actions.append({"tool": tag, "args": data})
                continue
        except (json.JSONDecodeError, TypeError):
            pass

        # AST/Pythonic Try
        if tag and tag.upper() != 'ACTION':
            parsed_args = _parse_pythonic_args(tag, content)
            if parsed_args:
                actions.append({"tool": tag, "args": parsed_args})
                continue

    # --- STRATEGY 3: NAKED CALLS (Fallback) ---
    # If the AI forgot the ::: syntax, we look for function calls starting with 'ai_'
    # Only run if we haven't found actions yet (to avoid duplicates)
    if not actions:
        # Regex: Matches "ai_word ( ... )"
        pattern_naked = r"(ai_\w+)\s*\((.*?)\)"
        matches_naked = re.finditer(pattern_naked, text, re.DOTALL)

        for match in matches_naked:
            tool_name = match.group(1)
            content = match.group(2)

            # Use the same AST logic
            parsed_args = _parse_pythonic_args(tool_name, content)
            if parsed_args:
                actions.append({"tool": tool_name, "args": parsed_args})

    return actions


def _parse_pythonic_args(tool_name, content):
    """Helper to parse (arg="val") strings via AST."""
    # Cleanup parens if regex captured them loosely
    content = content.strip()
    if content.startswith('(') and content.endswith(')'):
        content = content[1:-1]

    if not content:
        # Defaults
        if tool_name == 'ai_list_files': return {'path': '.'}
        return {}

    try:
        # Wrap in fake call
        tree = ast.parse(f"call({content})")
        call = tree.body[0].value

        kwargs = {k.arg: ast.literal_eval(k.value) for k in call.keywords}

        # Positional Mapping
        if call.args:
            mapping = {
                'ai_read_file': ['path', 'start_line', 'max_lines'],
                'ai_search_file': ['path', 'pattern'],
                'ai_list_files': ['path'],
                'ai_execute_task': ['head_id'],
            }.get(tool_name, [])

            for i, arg_val in enumerate(call.args):
                if i < len(mapping):
                    key = mapping[i]
                    if key not in kwargs:
                        kwargs[key] = ast.literal_eval(arg_val)

        return kwargs
    except Exception:
        # Last Resort Regex for key="val"
        args = {}
        kv_pattern = r"(\w+)\s*=\s*(?:['\"](.*?)['\"]|(\d+))"
        kv_matches = re.findall(kv_pattern, content)
        for k, v_str, v_int in kv_matches:
            if v_str is not None:
                args[k] = v_str
            else:
                args[k] = int(v_int)

        # Absolute desperation: plain string?
        if not args and content and "=" not in content:
            key = 'head_id' if 'execute' in tool_name else 'path'
            args[key] = content.strip("'\"")

        return args