"""
Tests for Layer 1 MCP tools (filesystem, fuzzy patch, memory, terminal, web, code, search, browser, vision).
"""
import json
import os
import shutil
from unittest.mock import patch

import pytest
from django.conf import settings
from django.db import connection

from parietal_lobe.parietal_mcp.gateway import ParietalMCP
from parietal_lobe.parietal_mcp.mcp_fs_functions.fuzzy_match import (
    STRATEGY_EXACT,
    find_match_span,
)
from parietal_lobe.parietal_mcp.mcp_fs_write import _write_sync


@pytest.mark.django_db
def test_mcp_fs_write_nested_relative_path():
    """Assert relative path under BASE_DIR writes UTF-8 and returns byte count."""
    rel = os.path.join('_pytest_mcp_fs', 'nested', 'out.txt')
    try:
        result = _write_sync(rel, 'hello layer1')
        assert result['ok'] is True
        assert result['bytes_written'] == len('hello layer1'.encode('utf-8'))
        full = os.path.join(str(settings.BASE_DIR), rel)
        with open(full, encoding='utf-8') as handle:
            assert handle.read() == 'hello layer1'
    finally:
        root = os.path.join(str(settings.BASE_DIR), '_pytest_mcp_fs')
        if os.path.isdir(root):
            shutil.rmtree(root, ignore_errors=True)


@pytest.mark.django_db
def test_mcp_fs_write_rejects_traversal():
    """Assert paths escaping project root are rejected."""
    result = _write_sync('../../outside.txt', 'x')
    assert result['ok'] is False
    err = result['error'].lower()
    assert 'denied' in err or 'outside' in err


@pytest.mark.django_db
def test_fuzzy_match_exact_strategy():
    """Assert exact substring match reports strategy 1."""
    body = 'alpha\nbeta\n'
    span = find_match_span(body, 'beta')
    assert span is not None
    _buf, _start, _end, strat = span
    assert strat == STRATEGY_EXACT


@pytest.mark.django_db
@patch('parietal_lobe.parietal_mcp.mcp_memory_sync.OllamaClient')
def test_mcp_memory_add(mock_ollama):
    """Assert add creates an Engram when embeddings are mocked."""
    mock_ollama.return_value.embed.return_value = [0.01] * 768
    from parietal_lobe.parietal_mcp.mcp_memory_sync import run_memory_action

    out = run_memory_action(
        'add',
        'agent_memory',
        'remember this fact',
        '',
        '',
        '',
        '',
        '',
    )
    assert out['action'] == 'add'
    assert out['entries_count'] >= 1
    assert 'engram_id' in out


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_mcp_terminal_blocks_rm_rf_root():
    """Assert rm -rf / is blocked without dangerous_cmd_override."""
    from parietal_lobe.parietal_mcp.mcp_terminal import mcp_terminal

    result = await mcp_terminal(
        command='rm -rf /',
        background=False,
        dangerous_cmd_override=False,
    )
    assert result.get('is_dangerous') is True


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_mcp_web_search_no_provider():
    """Assert missing providers surface an error or empty results."""
    from parietal_lobe.parietal_mcp.mcp_web_search import mcp_web_search

    with patch(
        'parietal_lobe.parietal_mcp.mcp_web_search._run_search',
        return_value={'error': 'none', 'results': [], 'query': 'django', 'count': 0},
    ):
        out = await mcp_web_search(query='django', max_results=3)
    assert 'error' in out or 'results' in out


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_mcp_code_exec_prints():
    """Assert trivial Python prints appear in combined output."""
    from parietal_lobe.parietal_mcp.mcp_code_exec import mcp_code_exec

    out = await mcp_code_exec(
        code='print("layer1_ok")',
        timeout=30,
        workdir=None,
    )
    blob = out.get('combined_preview') or out.get('stdout') or ''
    assert 'layer1_ok' in blob


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_mcp_session_search_shape():
    """Assert session search returns matches and count."""
    from parietal_lobe.parietal_mcp.mcp_session_search import mcp_session_search

    out = await mcp_session_search(
        query='test',
        limit=5,
        role_filter=None,
    )
    assert 'matches' in out
    assert 'count' in out


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_mcp_browser_unknown_action():
    """Assert unknown browser action returns error without Playwright."""
    from parietal_lobe.parietal_mcp.mcp_browser import mcp_browser

    out = await mcp_browser(action='not_a_real_action', session_id='s1')
    assert 'error' in out


@pytest.mark.django_db
@pytest.mark.asyncio
@patch('parietal_lobe.parietal_mcp.mcp_vision.litellm.completion')
@patch('parietal_lobe.parietal_mcp.mcp_vision._load_image_bytes')
async def test_mcp_vision_analysis(mock_load, mock_litellm):
    """Assert vision uses LiteLLM output when image bytes load."""
    mock_load.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
    mock_litellm.return_value = {
        'choices': [{'message': {'content': 'a red circle'}}],
    }
    from parietal_lobe.parietal_mcp.mcp_vision import mcp_vision

    out = await mcp_vision(
        image_path='/tmp/fake.png',
        question='what?',
        provider='openai/gpt-4o',
    )
    assert out.get('analysis') == 'a red circle'


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_gateway_json_string_for_dict_result():
    """Assert gateway JSON-encodes dict tool returns."""
    with patch(
        'parietal_lobe.parietal_mcp.mcp_fs_write._write_sync',
        return_value={'ok': True, 'path': 'x', 'bytes_written': 1},
    ):
        raw = await ParietalMCP.execute(
            'mcp_fs_write',
            {'path': 'x', 'content': 'y'},
        )
    data = json.loads(raw)
    assert data['ok'] is True


@pytest.mark.skipif(
    connection.vendor != 'postgresql',
    reason='PostgreSQL-only check for FTS environment.',
)
@pytest.mark.django_db
def test_session_search_vendor_postgres():
    """Assert connection is PostgreSQL when this test runs."""
    assert connection.vendor == 'postgresql'
