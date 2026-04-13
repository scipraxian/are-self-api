"""
Tests for Core Personal Agent MCP tools (filesystem, fuzzy patch, memory, terminal, web, code, search, browser, vision).
"""
import json
import os
import shutil
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import async_to_sync
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
        code='print("code_exec_print_ok")',
        timeout=30,
        workdir=None,
    )
    blob = out.get('combined_preview') or out.get('stdout') or ''
    assert 'code_exec_print_ok' in blob


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


def _ensure_reasoning_statuses():
    from frontal_lobe.models import ReasoningStatus, ReasoningStatusID

    ReasoningStatus.objects.get_or_create(
        pk=ReasoningStatusID.ACTIVE, defaults={'name': 'Active'}
    )
    ReasoningStatus.objects.get_or_create(
        pk=ReasoningStatusID.PENDING, defaults={'name': 'Pending'}
    )


def _make_ai_stack():
    from hypothalamus.models import AIModel, AIModelProvider, LLMProvider

    uid = uuid.uuid4().hex[:8]
    model = AIModel.objects.create(
        name='personal-agent-search-model-%s' % uid,
        context_length=4096,
    )
    provider = LLMProvider.objects.create(
        key='personal-agent-search-prov-%s' % uid,
        base_url='http://127.0.0.1',
    )
    amp = AIModelProvider.objects.create(
        ai_model=model,
        provider=provider,
        provider_unique_model_id='personal-agent-mid-%s' % uid,
    )
    return model, amp

def _simulate_basic_reasoning_session():
    _ensure_reasoning_statuses()
    from frontal_lobe.models import ReasoningSession, ReasoningTurn, ReasoningStatusID
    from hypothalamus.models import AIModelProviderUsageRecord

    model, amp = _make_ai_stack()
    session = ReasoningSession.objects.create(
        status_id=ReasoningStatusID.ACTIVE,
        total_xp=0,
    )
    ur = AIModelProviderUsageRecord.objects.create(
        ai_model_provider=amp,
        ai_model=model,
        request_payload={},
        response_payload={},
    )
    turn = ReasoningTurn.objects.create(
        session=session,
        turn_number=1,
        model_usage_record=ur,
        status_id=ReasoningStatusID.ACTIVE,
    )
    uid = uuid.uuid4().hex[:8]

    return ur, turn, uid


@pytest.mark.django_db
def test_mcp_session_search_empty_db():
    """Assert no rows yields zero matches."""
    from parietal_lobe.parietal_mcp.mcp_session_search import mcp_session_search

    out = async_to_sync(mcp_session_search)(
        query='zzzzunlikelytokenlayer1',
        limit=5,
        role_filter=None,
    )
    assert out['count'] == 0
    assert out['matches'] == []


@pytest.mark.django_db
def test_mcp_session_search_ledger_hit():
    """Assert a ReasoningTurn ledger match returns score and role."""
    _ensure_reasoning_statuses()
    from frontal_lobe.models import ReasoningSession, ReasoningTurn, ReasoningStatusID
    from hypothalamus.models import AIModelProviderUsageRecord
    from parietal_lobe.parietal_mcp.mcp_session_search import mcp_session_search

    model, amp = _make_ai_stack()
    session = ReasoningSession.objects.create(
        status_id=ReasoningStatusID.ACTIVE,
        total_xp=0,
    )
    keyword = 'ledgerhitlayer1token'
    ur = AIModelProviderUsageRecord.objects.create(
        ai_model_provider=amp,
        ai_model=model,
        request_payload={'messages': [{'role': 'user', 'content': keyword}]},
        response_payload={'choices': [{'message': {'content': 'ok'}}]},
    )
    ReasoningTurn.objects.create(
        session=session,
        turn_number=1,
        model_usage_record=ur,
        status_id=ReasoningStatusID.ACTIVE,
    )
    out = async_to_sync(mcp_session_search)(query=keyword, limit=5, role_filter='user')
    assert out['count'] >= 1
    hit = out['matches'][0]
    assert hit['session_id'] == str(session.id)
    assert 'score' in hit
    assert hit.get('role') == 'user'
    assert keyword in hit.get('content_snippet', '')


@pytest.mark.django_db
def test_mcp_session_search_toolcall_hit():
    """Assert ToolCall arguments are searchable with role_filter=tool."""
    from parietal_lobe.models import ToolCall, ToolDefinition
    from parietal_lobe.parietal_mcp.mcp_session_search import mcp_session_search

    ur, turn, uid = _simulate_basic_reasoning_session()
    td = ToolDefinition.objects.create(name='Layer1TC-%s' % uid)
    keyword = 'toolcallfindlayer1'
    ToolCall.objects.create(
        turn=turn,
        tool=td,
        arguments='{"q": "%s"}' % keyword,
        result_payload='done',
    )
    out = async_to_sync(mcp_session_search)(query=keyword, limit=5, role_filter='tool')
    assert out['count'] >= 1
    roles = {m.get('role') for m in out['matches']}
    assert 'tool' in roles


@pytest.mark.django_db
def test_mcp_session_search_role_lane_isolation():
    """Assert user / assistant / tool filters only surface the matching corpus."""
    _ensure_reasoning_statuses()
    from frontal_lobe.models import ReasoningSession, ReasoningTurn, ReasoningStatusID
    from hypothalamus.models import AIModelProviderUsageRecord
    from parietal_lobe.parietal_mcp.mcp_session_search import mcp_session_search

    model, amp = _make_ai_stack()
    session = ReasoningSession.objects.create(
        status_id=ReasoningStatusID.ACTIVE,
        total_xp=0,
    )
    user_kw = 'useronlylayer1aaa'
    asst_kw = 'assistantonlylayer1bbb'
    tool_kw = 'toolmsglayer1ccc'
    ur = AIModelProviderUsageRecord.objects.create(
        ai_model_provider=amp,
        ai_model=model,
        request_payload={
            'messages': [
                {'role': 'user', 'content': user_kw},
                {'role': 'assistant', 'content': 'nope'},
                {'role': 'tool', 'content': tool_kw},
            ]
        },
        response_payload={'choices': [{'message': {'content': asst_kw}}]},
    )
    ReasoningTurn.objects.create(
        session=session,
        turn_number=1,
        model_usage_record=ur,
        status_id=ReasoningStatusID.ACTIVE,
    )

    u = async_to_sync(mcp_session_search)(query=user_kw, limit=10, role_filter='user')
    assert u['count'] == 1

    ua = async_to_sync(mcp_session_search)(query=user_kw, limit=10, role_filter='assistant')
    assert ua['count'] == 0

    a = async_to_sync(mcp_session_search)(query=asst_kw, limit=10, role_filter='assistant')
    assert a['count'] == 1

    au = async_to_sync(mcp_session_search)(query=asst_kw, limit=10, role_filter='user')
    assert au['count'] == 0

    t = async_to_sync(mcp_session_search)(query=tool_kw, limit=10, role_filter='tool')
    assert t['count'] == 1
    assert all(m.get('role') == 'tool' for m in t['matches'])


@pytest.mark.django_db
def test_mcp_session_search_limit_capped():
    """Assert limit requests above 10 are capped."""
    from parietal_lobe.models import ToolCall, ToolDefinition
    from parietal_lobe.parietal_mcp.mcp_session_search import (
        SESSION_SEARCH_MAX_LIMIT,
        mcp_session_search,
    )

    ur, turn, uid = _simulate_basic_reasoning_session()
    td = ToolDefinition.objects.create(name='Layer1Many-%s' % uid)
    kw = 'manymatchlayer1'
    for _ in range(SESSION_SEARCH_MAX_LIMIT + 4):
        ToolCall.objects.create(
            turn=turn,
            tool=td,
            arguments='{"x": "%s"}' % kw,
            result_payload='',
        )
    out = async_to_sync(mcp_session_search)(query=kw, limit=99, role_filter='tool')
    assert len(out['matches']) <= SESSION_SEARCH_MAX_LIMIT


@pytest.mark.django_db
def test_mcp_browser_click_uses_ref_attr():
    """Assert click with @e1 targets data-parietal-browser-ref locator."""
    from parietal_lobe.parietal_mcp import mcp_browser as mb

    mock_loc = MagicMock()
    mock_loc.click = AsyncMock()
    mock_page = AsyncMock()
    mock_page.locator = MagicMock(return_value=mock_loc)
    mock_page.evaluate = AsyncMock(side_effect=[2, ['@e1 a name="" text=""']])
    mb._pages['ref-session'] = mock_page
    try:
        out = async_to_sync(mb.mcp_browser)(
            action='click',
            session_id='ref-session',
            ref='@e1',
        )
        mock_page.locator.assert_called_with(
            '[%s="1"]' % mb.BROWSER_REF_ATTR,
        )
        mock_loc.click.assert_awaited()
        assert out.get('success') is True
    finally:
        mb._pages.pop('ref-session', None)


@pytest.mark.django_db
def test_mcp_browser_click_css_fallback():
    """Assert non-ref strings are passed through as CSS selectors."""
    from parietal_lobe.parietal_mcp import mcp_browser as mb

    mock_loc = MagicMock()
    mock_loc.click = AsyncMock()
    mock_page = AsyncMock()
    mock_page.locator = MagicMock(return_value=mock_loc)
    mock_page.evaluate = AsyncMock(side_effect=[0, []])
    mb._pages['css-session'] = mock_page
    try:
        async_to_sync(mb.mcp_browser)(
            action='click',
            session_id='css-session',
            ref='#submit-btn',
        )
        mock_page.locator.assert_called_with('#submit-btn')
    finally:
        mb._pages.pop('css-session', None)


@pytest.mark.django_db
def test_mcp_browser_close_removes_page():
    """Assert close drops the session page from the registry."""
    from parietal_lobe.parietal_mcp import mcp_browser as mb

    mock_page = AsyncMock()
    mb._pages['close-sess'] = mock_page
    try:
        out = async_to_sync(mb.mcp_browser)(action='close', session_id='close-sess')
        assert out.get('closed') is True
        assert 'close-sess' not in mb._pages
        mock_page.close.assert_awaited()
    finally:
        mb._pages.pop('close-sess', None)


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
    reason='PostgreSQL-only FTS exercise.',
)
@pytest.mark.django_db
def test_session_search_postgresql_fts_returns_scored_match():
    """Assert PostgreSQL path returns a scored ledger hit."""
    _ensure_reasoning_statuses()
    from frontal_lobe.models import ReasoningSession, ReasoningTurn, ReasoningStatusID
    from hypothalamus.models import AIModelProviderUsageRecord
    from parietal_lobe.parietal_mcp.mcp_session_search import mcp_session_search

    assert connection.vendor == 'postgresql'
    model, amp = _make_ai_stack()
    session = ReasoningSession.objects.create(
        status_id=ReasoningStatusID.ACTIVE,
        total_xp=0,
    )
    kw = 'pgftskeywordlayer1'
    ur = AIModelProviderUsageRecord.objects.create(
        ai_model_provider=amp,
        ai_model=model,
        request_payload={'messages': [{'role': 'user', 'content': kw}]},
        response_payload={},
    )
    ReasoningTurn.objects.create(
        session=session,
        turn_number=1,
        model_usage_record=ur,
        status_id=ReasoningStatusID.ACTIVE,
    )
    out = async_to_sync(mcp_session_search)(query=kw, limit=5, role_filter='user')
    assert out['count'] >= 1
    assert isinstance(out['matches'][0].get('score'), (int, float))
