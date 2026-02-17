from asgiref.sync import sync_to_async
from django.apps import apps


@sync_to_async
def _read_field_sync(app_label: str, model_name: str, record_id: str,
                     field_name: str, start_line: int, max_lines: int) -> str:
    try:
        model_class = apps.get_model(app_label, model_name)
    except LookupError:
        return f"Error: Model '{app_label}.{model_name}' not found."

    try:
        record = model_class.objects.get(pk=record_id)
    except model_class.DoesNotExist:
        return f"Error: Record {record_id} not found in {model_name}."

    val = getattr(record, field_name, None)
    if val is None:
        return f"Field '{field_name}' is empty or null."

    text_val = str(val)
    lines = text_val.split('\n')
    total_lines = len(lines)

    start_idx = max(0, start_line - 1)
    end_idx = start_idx + max_lines
    chunk = lines[start_idx:end_idx]

    content = "".join(
        [f"{i + 1}: {line}\n" for i, line in enumerate(chunk, start=start_idx)])
    if end_idx < total_lines:
        content += (f"... [Displaying lines {start_idx + 1}-"
                    f"{min(end_idx, total_lines)} of {total_lines}. Use"
                    f" start_line={end_idx + 1} to read more.]")

    return content


async def mcp_read_record_field(app_label: str, model_name: str, record_id: str,
                                field_name: str, start_line: int = 1,
                                max_lines: int = 50) -> str:
    """MCP Tool: Reads a specific text field from the database in chunks."""
    return await _read_field_sync(app_label, model_name, record_id, field_name,
                                  start_line, max_lines)
