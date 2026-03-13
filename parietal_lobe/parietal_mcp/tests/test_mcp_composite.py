import asyncio
import os

import pytest

from parietal_lobe.parietal_mcp.gateway import ParietalMCP


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_fs_read(tmp_path):
    """Tests the mcp_fs read action via the gateway."""
    test_file = tmp_path / 'test_read.txt'
    test_file.write_text(
        'Line 1: Hello World\nLine 2: Testing MCP FS\nLine 3: Done',
        encoding='utf-8',
    )

    result = await ParietalMCP.execute('mcp_fs', {
        'action': 'read',
        'params': {'path': str(test_file)},
    })

    assert 'Hello World' in result
    assert 'Testing MCP FS' in result


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_fs_list(tmp_path):
    """Tests the mcp_fs list action via the gateway."""
    (tmp_path / 'alpha.py').write_text('pass', encoding='utf-8')
    (tmp_path / 'beta.txt').write_text('data', encoding='utf-8')

    result = await ParietalMCP.execute('mcp_fs', {
        'action': 'list',
        'params': {'path': str(tmp_path)},
    })

    assert 'alpha.py' in result
    assert 'beta.txt' in result


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_fs_grep(tmp_path):
    """Tests the mcp_fs grep action via the gateway."""
    test_file = tmp_path / 'searchable.py'
    test_file.write_text(
        'def hello():\n    return "NEEDLE_VALUE"\n\nprint("done")',
        encoding='utf-8',
    )

    result = await ParietalMCP.execute('mcp_fs', {
        'action': 'grep',
        'params': {'path': str(test_file), 'pattern': 'NEEDLE_VALUE'},
    })

    assert 'NEEDLE_VALUE' in result


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_fs_patch_create(tmp_path):
    """Tests the mcp_fs patch action to create a new file."""
    new_file = tmp_path / 'created.txt'

    result = await ParietalMCP.execute('mcp_fs', {
        'action': 'patch',
        'params': {
            'path': str(new_file),
            'content': 'Fresh content here.',
            'create': True,
        },
    })

    assert 'Success' in result
    assert new_file.read_text(encoding='utf-8') == 'Fresh content here.'


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_fs_patch_line_replace(tmp_path):
    """Tests the mcp_fs patch action to replace specific lines."""
    target = tmp_path / 'existing.py'
    target.write_text(
        'line 1\nline 2\nline 3\nline 4\n',
        encoding='utf-8',
    )

    result = await ParietalMCP.execute('mcp_fs', {
        'action': 'patch',
        'params': {
            'path': str(target),
            'content': 'REPLACED LINE 2\nREPLACED LINE 3',
            'start_line': 2,
            'end_line': 3,
        },
    })

    assert 'Success' in result
    lines = target.read_text(encoding='utf-8').splitlines()
    assert lines[0] == 'line 1'
    assert lines[1] == 'REPLACED LINE 2'
    assert lines[2] == 'REPLACED LINE 3'
    assert lines[3] == 'line 4'


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_fs_invalid_action():
    """Tests that an invalid action returns a clear error."""
    result = await ParietalMCP.execute('mcp_fs', {
        'action': 'delete',
        'params': {'path': '/tmp/anything'},
    })

    assert 'Error' in result
    assert 'Invalid action' in result


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_fs_blocked_path(tmp_path):
    """Tests that blocked paths are rejected."""
    result = await ParietalMCP.execute('mcp_fs', {
        'action': 'read',
        'params': {'path': str(tmp_path / 'venv' / 'lib' / 'site.py')},
    })

    assert 'Error' in result
    assert 'blocked' in result.lower() or 'denied' in result.lower()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_git_status():
    """Tests the mcp_git status action on the current repo."""
    result = await ParietalMCP.execute('mcp_git', {
        'action': 'status',
        'params': {},
    })

    # Should return something — either branch info or clean status
    assert result is not None
    assert len(result) > 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_git_log():
    """Tests the mcp_git log action on the current repo."""
    result = await ParietalMCP.execute('mcp_git', {
        'action': 'log',
        'params': {'count': 5, 'oneline': True},
    })

    assert result is not None
    assert len(result) > 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_git_diff():
    """Tests the mcp_git diff action on the current repo."""
    result = await ParietalMCP.execute('mcp_git', {
        'action': 'diff',
        'params': {},
    })

    assert result is not None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_git_branch():
    """Tests the mcp_git branch list action."""
    result = await ParietalMCP.execute('mcp_git', {
        'action': 'branch',
        'params': {},
    })

    assert result is not None
    assert len(result) > 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_git_invalid_action():
    """Tests that an invalid git action returns a clear error."""
    result = await ParietalMCP.execute('mcp_git', {
        'action': 'push',
        'params': {},
    })

    assert 'Error' in result
    assert 'Invalid git action' in result
