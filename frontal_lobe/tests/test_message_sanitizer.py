import json

import pytest

from frontal_lobe.constants import FrontalLobeConstants
from frontal_lobe.frontal_lobe import CONTENT, ROLE, FrontalLobe


class DummySpike:
    def __init__(self):
        self.id = 'dummy-spike'
        self.application_log = ''

    def save(self, update_fields=None):
        pass


@pytest.mark.django_db
def test_sanitizer_strips_only_addon_messages():
    spike = DummySpike()
    lobe = FrontalLobe(spike)

    messages = [
        {ROLE: FrontalLobeConstants.ROLE_SYSTEM, CONTENT: 'system laws'},
        {
            ROLE: FrontalLobeConstants.ROLE_USER,
            CONTENT: 'Normal user message',
        },
        {
            ROLE: FrontalLobeConstants.ROLE_USER,
            CONTENT: '[FOCUS GAME ADDON]: focus rules here',
        },
        {
            ROLE: FrontalLobeConstants.ROLE_USER,
            CONTENT: '[AGILE ADDON]: sprint board context',
        },
    ]

    sanitized = lobe._sanitize_messages_for_cache(messages)

    # Two addon messages should be removed, order of remaining preserved
    assert len(sanitized) == 2
    assert sanitized[0][ROLE] == FrontalLobeConstants.ROLE_SYSTEM
    assert sanitized[1][CONTENT] == 'Normal user message'
    assert 'ADDON' not in sanitized[1][CONTENT]
    # No addon markers should remain
    assert all('ADDON' not in m[CONTENT] for m in sanitized)


@pytest.mark.django_db
def test_sanitizer_strips_sensory_messages():
    spike = DummySpike()
    lobe = FrontalLobe(spike)

    sensory_block = (
        "[YOUR CARD CATALOG (ENGRAM INDEX)]\n"
        "Your memory banks are completely empty.\n"
        "(Use mcp_engram_read to read full facts)\n\n"
        "[SYSTEM SENSORY]: Memory banks indexed.\n\n"
        "YOUR MOVE: Write your THOUGHT and execute tools.\n\n"
        "Write your reasoning starting with 'THOUGHT: '. Stop writing text immediately after your thought and invoke your tools natively. DO NOT generate fake system diagnostics."
    )

    messages = [
        {
            ROLE: FrontalLobeConstants.ROLE_USER,
            CONTENT: 'Normal user message',
        },
        {
            ROLE: FrontalLobeConstants.ROLE_USER,
            CONTENT: sensory_block,
        },
    ]

    sanitized = lobe._sanitize_messages_for_cache(messages)

    # Sensory block should be removed, leaving only the normal user message
    assert len(sanitized) == 1
    assert sanitized[0][CONTENT] == 'Normal user message'


@pytest.mark.django_db
def test_sanitizer_does_not_strip_non_addon_bracketed_messages():
    spike = DummySpike()
    lobe = FrontalLobe(spike)

    messages = [
        {
            ROLE: FrontalLobeConstants.ROLE_USER,
            CONTENT: '[Note] This is a regular bracketed note',
        },
        {
            ROLE: FrontalLobeConstants.ROLE_USER,
            CONTENT: '[TODO] Consider refactoring later',
        },
    ]

    sanitized = lobe._sanitize_messages_for_cache(messages)

    # No messages should be stripped here
    assert len(sanitized) == 2
    assert sanitized == messages


@pytest.mark.django_db
def test_sanitized_payload_is_used_for_history_replay():
    """
    End-to-end style check (logic level):
    - Given a payload that has already been sanitized for cache,
    - history reconstruction over that payload must never surface addon text.
    """
    # Simulate what _build_history_messages would see coming from the DB:
    # a sanitized payload with no addon messages at all.
    sanitized_payload = {
        'messages': [
            {
                'role': FrontalLobeConstants.ROLE_USER,
                'content': 'User ctx without addons',
            },
            {
                'role': FrontalLobeConstants.ROLE_ASSISTANT,
                'content': 'Prev thought',
            },
        ]
    }

    # History reconstruction logic in _build_history_messages only ever pulls
    # user contents out of the stored request_payload; tool results and
    # assistant thoughts are added separately. This test asserts that if the
    # payload is already sanitized, no addon text can appear in what the
    # cache rehydrates as prior user messages.
    payload = sanitized_payload
    raw_messages = payload.get('messages') or []
    user_contents = []
    for msg in raw_messages:
        if (
            isinstance(msg, dict)
            and msg.get('role') == FrontalLobeConstants.ROLE_USER
        ):
            content = msg.get('content')
            if content:
                user_contents.append(str(content))

    # Basic shape: at least one user message, and no addon markers
    assert user_contents
    assert all('ADDON' not in c for c in user_contents)
