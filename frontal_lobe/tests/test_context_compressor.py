"""Tests for context window compression."""

from django.test import SimpleTestCase

from common.tests.common_test_case import CommonFixturesAPITestCase
from frontal_lobe.context_compressor import (
    SUMMARY_SENTINEL,
    TOOL_PLACEHOLDER_PREFIX,
    ContextCompressor,
    estimate_message_list_tokens,
    estimate_tokens,
    messages_already_summarized,
    aggressive_prune_to_latest_tool,
    prune_inner_tool_messages,
)
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
    ReasoningTurnKindID,
)


class TestEstimateTokens(SimpleTestCase):
    """Assert token heuristics behave predictably."""

    def test_estimate_tokens_empty(self):
        self.assertEqual(estimate_tokens(''), 0)

    def test_estimate_tokens_length(self):
        text = 'a' * 400
        self.assertEqual(estimate_tokens(text), 100)

    def test_estimate_within_twenty_percent_band(self):
        """Assert rough heuristic stays within a loose band vs char/4."""
        text = (
            'The quick brown fox jumps over the lazy dog. ' * 50
        )
        est = estimate_tokens(text)
        baseline = len(text) // 4
        self.assertLessEqual(abs(est - baseline), max(1, baseline // 5))


class TestPruneInnerToolMessages(SimpleTestCase):
    """Assert inner tool pruning keeps first two and last two tool messages."""

    def test_no_change_when_four_or_fewer_tools(self):
        msgs = [
            {'role': 'tool', 'name': 'a', 'content': '1'},
            {'role': 'tool', 'name': 'b', 'content': '2'},
            {'role': 'tool', 'name': 'c', 'content': '3'},
            {'role': 'tool', 'name': 'd', 'content': '4'},
        ]
        out = prune_inner_tool_messages(msgs)
        self.assertEqual(out, msgs)

    def test_replaces_middle_tool_messages(self):
        msgs = []
        for i in range(6):
            msgs.append({'role': 'tool', 'name': f't{i}', 'content': f'body{i}'})
        out = prune_inner_tool_messages(msgs)
        self.assertTrue(out[0]['content'].startswith('body'))
        self.assertTrue(out[1]['content'].startswith('body'))
        self.assertTrue(out[4]['content'].startswith('body'))
        self.assertTrue(out[5]['content'].startswith('body'))
        for j in (2, 3):
            self.assertIn(TOOL_PLACEHOLDER_PREFIX, out[j]['content'])
            self.assertIn(f't{j}', out[j]['content'])


class TestAggressivePruneToLatestTool(SimpleTestCase):
    """Assert aggressive pruning keeps only the last tool result."""

    def test_keeps_last_tool_only(self):
        msgs = [
            {'role': 'system', 'content': 'sys'},
            {'role': 'user', 'content': 'u'},
            {'role': 'tool', 'name': 'x', 'content': 't1'},
            {'role': 'tool', 'name': 'y', 'content': 't2'},
            {'role': 'assistant', 'content': 'done'},
        ]
        out = aggressive_prune_to_latest_tool(msgs)
        tool_roles = [m for m in out if m['role'] == 'tool']
        self.assertEqual(len(tool_roles), 1)
        self.assertEqual(tool_roles[0]['content'], 't2')


class TestIdempotence(SimpleTestCase):
    """Assert repeated compression does not duplicate summaries."""

    def test_messages_already_summarized_detects_sentinel(self):
        msgs = [
            {'role': 'assistant', 'content': f'{SUMMARY_SENTINEL}\nhello'},
        ]
        self.assertTrue(messages_already_summarized(msgs))


class TestContextCompressorIntegration(CommonFixturesAPITestCase):
    """Assert ContextCompressor DB side effects."""

    def setUp(self):
        super().setUp()
        self.session = ReasoningSession.objects.create(
            status_id=ReasoningStatusID.ACTIVE,
        )

    def test_no_compression_below_threshold(self):
        msgs = [{'role': 'user', 'content': 'hi'}]
        comp = ContextCompressor(self.session)
        out = comp.compress(msgs, threshold_tokens=10_000)
        self.assertEqual(out, msgs)

    def test_middle_summary_creates_summary_turn(self):
        long_middle = 'word ' * 5000
        msgs = [
            {'role': 'system', 'content': 'sys'},
            {'role': 'user', 'content': 'first'},
            {'role': 'assistant', 'content': long_middle},
            {'role': 'user', 'content': 'last user'},
        ]

        def summarize_fn(_text: str) -> str:
            return 'short summary.'

        comp = ContextCompressor(self.session)
        ReasoningTurn.objects.create(
            session=self.session,
            turn_number=1,
            status_id=ReasoningStatusID.COMPLETED,
            turn_kind_id=ReasoningTurnKindID.NORMAL,
        )
        out = comp.compress(
            msgs,
            threshold_tokens=100,
            summarize_fn=summarize_fn,
        )
        self.assertTrue(any(SUMMARY_SENTINEL in str(m.get('content', '')) for m in out))
        summary_turns = ReasoningTurn.objects.filter(
            session=self.session,
            turn_kind_id=ReasoningTurnKindID.SUMMARY,
        )
        self.assertEqual(summary_turns.count(), 1)
