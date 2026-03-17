import asyncio
import os


def _list_sync(path: str) -> str:
    if not os.path.exists(path):
        return f"Error: '{path}' not found."
    if not os.path.isdir(path):
        return f"Error: '{path}' is not a directory."

    try:
        items = os.listdir(path)
        items.sort()

        result = [f'Listing for: {path}']
        for item in items[:50]:
            item_path = os.path.join(path, item)
            kind = '[DIR] ' if os.path.isdir(item_path) else '[FILE]'
            result.append(f'{kind} {item}')

        if len(items) > 50:
            result.append(f'... (and {len(items) - 50} more)')

        return '\n'.join(result)
    except Exception as e:
        return f'Error listing directory: {str(e)}'


async def execute(path: str) -> str:
    """Lists files and directories at a specific path."""
    return await asyncio.to_thread(_list_sync, path)
