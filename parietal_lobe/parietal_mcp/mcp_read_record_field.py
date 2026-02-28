from asgiref.sync import sync_to_async

from common.queries import guess_model


@sync_to_async
def _read_field_sync(
    model_name: str, record_id: str, field_name: str, page: int
) -> str:
    result = guess_model(model_name)
    if not result.success:
        return result.message

    model_class = result.model_class

    try:
        record = model_class.objects.get(pk=record_id)
    except Exception as e:
        return f'Database Error: {str(e)}'

    val = getattr(record, field_name, None)
    if not val:
        return f"Field '{field_name}' is empty or null."

    page_size = 350  # HARD CAP
    lines = str(val).split('\n')
    total_lines = len(lines)
    total_pages = max(1, (total_lines + page_size - 1) // page_size)

    safe_page = max(1, min(int(page), total_pages))
    start_idx = (safe_page - 1) * page_size
    end_idx = start_idx + page_size

    chunk = lines[start_idx:end_idx]
    content = ''.join(
        [f'{i + 1}: {line}\n' for i, line in enumerate(chunk, start=start_idx)]
    )

    if safe_page < total_pages:
        content += f'\n... [PAGE {safe_page} of {total_pages}. Request page={safe_page + 1} to read more.]'
    else:
        content += f'\n... [END OF RECORD (Page {safe_page}/{total_pages})]'

    return content


async def mcp_read_record_field(
    model_name: str,
    record_id: str,
    field_name: str,
    page: int = 1,
) -> str:
    """MCP Tool: Reads a specific database text field via pagination."""
    return await _read_field_sync(model_name, record_id, field_name, page)
