import re

from asgiref.sync import sync_to_async
from django.apps import apps


@sync_to_async
def _search_field_sync(app_label: str, model_name: str, record_id: str,
                       field_name: str, pattern: str) -> str:
    try:
        model_class = apps.get_model(app_label, model_name)
    except LookupError:
        return f"Error: Model '{app_label}.{model_name}' not found."

    try:
        record = model_class.objects.get(pk=record_id)
    except model_class.DoesNotExist:
        return f"Error: Record {record_id} not found."

    val = getattr(record, field_name, None)
    if not val:
        return f"Field '{field_name}' is empty or null."

    lines = str(val).split('\n')
    results = []
    matches_found = 0
    context_lines = 2

    for i, line in enumerate(lines):
        if re.search(pattern, line, re.IGNORECASE):
            matches_found += 1
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            chunk = "".join([f"{idx + 1}: {l}\n" for idx, l in
                             enumerate(lines[start:end], start=start)])
            results.append(
                f"--- Match {matches_found} (Line {i + 1}) ---\n{chunk}")
            if len(results) >= 10:
                results.append("... [Limit Reached]")
                break

    return "\n".join(
        results) if results else f"No matches found for '{pattern}'."


async def mcp_search_record_field(app_label: str, model_name: str,
                                  record_id: str, field_name: str,
                                  pattern: str) -> str:
    """MCP Tool: Searches a specific text field in the database for a regex
    pattern."""
    return await _search_field_sync(app_label, model_name, record_id,
                                    field_name, pattern)
