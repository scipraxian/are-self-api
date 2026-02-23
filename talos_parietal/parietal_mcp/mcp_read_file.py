import asyncio
import os


def _read_sync(path: str, page: int) -> str:
    if not os.path.exists(path):
        return f"Error: '{path}' not found."
    if os.path.isdir(path):
        return f"Error: '{path}' is a directory."

    page_size = 50  # HARD CAP

    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        total_lines = len(lines)
        total_pages = max(1, (total_lines + page_size - 1) // page_size)

        # Clamp page number
        safe_page = max(1, min(page, total_pages))
        start_idx = (safe_page - 1) * page_size
        end_idx = start_idx + page_size

        chunk = lines[start_idx:end_idx]
        content = ''.join(
            [
                f'{i + 1}: {line}'
                for i, line in enumerate(chunk, start=start_idx)
            ]
        )

        if safe_page < total_pages:
            content += f'\n\n... [PAGE {safe_page} of {total_pages}. Request page={safe_page + 1} to read more.]'
        else:
            content += f'\n\n... [END OF FILE (Page {safe_page}/{total_pages})]'

        return content
    except Exception as e:
        return f'Error reading file: {str(e)}'


async def mcp_read_file(path: str, page: int = 1) -> str:
    """MCP Tool: Reads a file surgically using pagination."""
    return await asyncio.to_thread(_read_sync, path, int(page))
