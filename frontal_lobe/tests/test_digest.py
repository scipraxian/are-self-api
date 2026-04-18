"""Tests for the ReasoningTurnDigest signal and builder.

Two classes, split by layer:

* ``DigestSignalTest`` exercises the ``post_save`` receiver in
  ``frontal_lobe.signals`` — skip paths, broadcast wiring, idempotence,
  failure isolation.
* ``DigestBuilderTest`` exercises the pure builder functions in
  ``frontal_lobe.digest_builder`` directly — excerpt extraction across
  payload shapes, tool-call summary, engram IDs, idempotence, and the
  push/pull shape symmetry (``DigestSerializer`` vs
  ``digest_to_vesicle``).
"""

import json
import logging
from unittest.mock import AsyncMock, patch

from common.tests.common_test_case import CommonTestCase
from frontal_lobe import digest_builder
from frontal_lobe import signals as digest_signals
from frontal_lobe.digest_builder import (
    build_and_save_digest,
    build_digest_payload,
    build_engram_ids,
    build_tool_calls_summary,
    digest_to_vesicle,
    extract_excerpt,
    resolve_model_name,
)
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatus,
    ReasoningStatusID,
    ReasoningTurn,
    ReasoningTurnDigest,
)
from frontal_lobe.serializers import DigestSerializer
from hippocampus.models import Engram
from hypothalamus.models import (
    AIModel,
    AIModelProvider,
    AIModelProviderUsageRecord,
    LLMProvider,
)
from parietal_lobe.models import ToolCall, ToolDefinition


# ---------------------------------------------------------------------------
# Shared setup helpers
# ---------------------------------------------------------------------------


def _make_session_graph(test):
    """Populate test with session, model/provider chain, and a tool.

    Kept flat (module-level) per the style guide: no nested functions.
    """
    test.ai_model = AIModel.objects.create(
        name='test-model', context_length=4096
    )
    test.llm_provider = LLMProvider.objects.create(
        key='test-provider', base_url='http://test.local'
    )
    test.ai_model_provider = AIModelProvider.objects.create(
        ai_model=test.ai_model,
        provider=test.llm_provider,
        provider_unique_model_id='test-model-id',
    )
    test.session = ReasoningSession.objects.create(
        status_id=ReasoningStatusID.ACTIVE
    )
    test.tool = ToolDefinition.objects.create(name='test_tool')


def _make_usage_record(
    request_payload=None,
    response_payload=None,
    input_tokens=7,
    output_tokens=9,
    ai_model_provider=None,
):
    """Create a bare AIModelProviderUsageRecord for a turn to point at."""
    return AIModelProviderUsageRecord.objects.create(
        request_payload=request_payload or {},
        response_payload=response_payload or {},
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        ai_model_provider=ai_model_provider,
    )


# ---------------------------------------------------------------------------
# Signal tests
# ---------------------------------------------------------------------------


class DigestSignalTest(CommonTestCase):
    """Assert the post_save receiver wires the digest and broadcast."""

    def setUp(self):
        super().setUp()
        _make_session_graph(self)

    def test_turn_without_usage_record_skips_digest_and_broadcast(self):
        """Assert turns with no usage record produce neither digest nor push."""
        with patch(
            'frontal_lobe.signals.fire_neurotransmitter',
            new_callable=AsyncMock,
        ) as mock_fire:
            turn = ReasoningTurn.objects.create(
                session=self.session,
                turn_number=1,
                status_id=ReasoningStatusID.ACTIVE,
            )

        self.assertFalse(
            ReasoningTurnDigest.objects.filter(turn=turn).exists()
        )
        mock_fire.assert_not_called()

    def test_turn_with_usage_record_writes_digest_and_broadcasts(self):
        """Assert a usage-record turn produces a digest and one Acetylcholine."""
        usage = _make_usage_record(
            response_payload={'role': 'assistant', 'content': 'Hello world'},
            input_tokens=11,
            output_tokens=22,
            ai_model_provider=self.ai_model_provider,
        )
        with patch(
            'frontal_lobe.signals.fire_neurotransmitter',
            new_callable=AsyncMock,
        ) as mock_fire:
            turn = ReasoningTurn.objects.create(
                session=self.session,
                turn_number=1,
                status_id=ReasoningStatusID.COMPLETED,
                model_usage_record=usage,
            )

        digest = ReasoningTurnDigest.objects.get(turn=turn)
        self.assertEqual(digest.turn_number, 1)
        self.assertEqual(digest.tokens_in, 11)
        self.assertEqual(digest.tokens_out, 22)
        self.assertEqual(digest.model_name, 'test-model')
        self.assertEqual(digest.excerpt, 'Hello world')

        self.assertEqual(mock_fire.call_count, 1)
        transmitter = mock_fire.call_args.args[0]
        self.assertEqual(transmitter.receptor_class, 'ReasoningTurnDigest')
        self.assertEqual(transmitter.dendrite_id, str(turn.id))
        self.assertEqual(transmitter.activity, 'saved')
        self.assertEqual(transmitter.vesicle['turn_id'], str(turn.id))
        self.assertEqual(transmitter.vesicle['session_id'], str(self.session.id))

    def test_second_save_is_idempotent(self):
        """Assert re-saving a turn leaves exactly one digest row."""
        usage = _make_usage_record(
            response_payload={'role': 'assistant', 'content': 'Hi'},
        )
        turn = ReasoningTurn.objects.create(
            session=self.session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
            model_usage_record=usage,
        )
        first_pk = ReasoningTurnDigest.objects.get(turn=turn).pk

        turn.status_id = ReasoningStatusID.COMPLETED
        turn.save(update_fields=['status'])

        self.assertEqual(
            ReasoningTurnDigest.objects.filter(turn=turn).count(), 1
        )
        self.assertEqual(
            ReasoningTurnDigest.objects.get(turn=turn).pk, first_pk
        )

    def test_raw_true_fixture_load_skips_digest(self):
        """Assert raw=True fixture loads bypass the receiver entirely."""
        usage = _make_usage_record(
            response_payload={'role': 'assistant', 'content': 'raw'},
        )
        turn = ReasoningTurn(
            session=self.session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
            model_usage_record=usage,
        )
        turn.save()
        # Drop the digest the normal save just wrote so we can prove the
        # raw=True call does not re-create one.
        ReasoningTurnDigest.objects.filter(turn=turn).delete()

        with patch(
            'frontal_lobe.signals.fire_neurotransmitter',
            new_callable=AsyncMock,
        ) as mock_fire:
            digest_signals.write_reasoning_turn_digest(
                sender=ReasoningTurn,
                instance=turn,
                raw=True,
                created=False,
                using='default',
                update_fields=None,
            )

        self.assertFalse(
            ReasoningTurnDigest.objects.filter(turn=turn).exists()
        )
        mock_fire.assert_not_called()

    def test_build_failure_logs_and_suppresses_broadcast(self):
        """Assert builder errors are logged and the broadcast is skipped."""
        usage = _make_usage_record(
            response_payload={'role': 'assistant', 'content': 'boom'},
        )
        with patch(
            'frontal_lobe.signals.build_and_save_digest',
            side_effect=RuntimeError('builder exploded'),
        ), patch(
            'frontal_lobe.signals.fire_neurotransmitter',
            new_callable=AsyncMock,
        ) as mock_fire, self.assertLogs(
            'frontal_lobe.signals', level=logging.ERROR
        ) as log_ctx:
            turn = ReasoningTurn.objects.create(
                session=self.session,
                turn_number=1,
                status_id=ReasoningStatusID.ACTIVE,
                model_usage_record=usage,
            )

        self.assertFalse(
            ReasoningTurnDigest.objects.filter(turn=turn).exists()
        )
        mock_fire.assert_not_called()
        self.assertTrue(
            any(
                '[FrontalLobe] Failed to build digest for turn' in line
                for line in log_ctx.output
            )
        )


# ---------------------------------------------------------------------------
# Builder tests
# ---------------------------------------------------------------------------


class DigestBuilderTest(CommonTestCase):
    """Assert pure-function builders extract the right shapes."""

    def setUp(self):
        super().setUp()
        _make_session_graph(self)
        self.turn = ReasoningTurn.objects.create(
            session=self.session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )

    # --- excerpt ----------------------------------------------------------

    def test_extract_excerpt_direct_shape(self):
        """Assert direct {role, content} shape yields the content."""
        usage = _make_usage_record(
            response_payload={'role': 'assistant', 'content': 'Hello world'}
        )
        self.assertEqual(extract_excerpt(usage), 'Hello world')

    def test_extract_excerpt_openai_shape(self):
        """Assert OpenAI choices[0].message shape yields the content."""
        usage = _make_usage_record(
            response_payload={
                'choices': [
                    {
                        'message': {
                            'role': 'assistant',
                            'content': 'Hello world',
                        }
                    }
                ]
            }
        )
        self.assertEqual(extract_excerpt(usage), 'Hello world')

    def test_extract_excerpt_mcp_respond_fallback(self):
        """Assert mcp_respond_to_user.thought replaces empty content."""
        base = {
            'role': 'assistant',
            'content': '',
            'tool_calls': [
                {
                    'function': {
                        'name': 'mcp_respond_to_user',
                        'arguments': None,
                    }
                }
            ],
        }
        # Arguments as JSON string.
        base['tool_calls'][0]['function']['arguments'] = json.dumps(
            {'thought': 'Thinking out loud'}
        )
        usage_str = _make_usage_record(response_payload=base)
        self.assertEqual(extract_excerpt(usage_str), 'Thinking out loud')

        # Arguments as dict.
        base['tool_calls'][0]['function']['arguments'] = {
            'thought': 'Thinking out loud'
        }
        usage_dict = _make_usage_record(response_payload=base)
        self.assertEqual(extract_excerpt(usage_dict), 'Thinking out loud')

    def test_extract_excerpt_truncation(self):
        """Assert 400-char content truncates to exactly 300 chars with U+2026."""
        long_content = 'x' * 400
        usage = _make_usage_record(
            response_payload={'role': 'assistant', 'content': long_content}
        )
        excerpt = extract_excerpt(usage)
        self.assertEqual(len(excerpt), digest_builder.EXCERPT_MAX_LEN)
        self.assertEqual(excerpt[-1], digest_builder.ELLIPSIS)

    def test_extract_excerpt_malformed_payloads(self):
        """Assert malformed response_payloads resolve to the empty string."""
        malformed = [
            None,
            {},
            'not a dict',
            {'choices': []},
            {'choices': [{}]},
            {'choices': [{'message': None}]},
            {'choices': [{'message': {'content': 123}}]},
        ]
        for payload in malformed:
            with self.subTest(payload=payload):
                usage = _make_usage_record(response_payload=payload)
                self.assertEqual(extract_excerpt(usage), '')

    # --- model name -------------------------------------------------------

    def test_resolve_model_name_missing_chain(self):
        """Assert broken FK chains resolve to '' and full chain resolves."""
        self.assertEqual(resolve_model_name(None), '')

        orphan = _make_usage_record()
        self.assertEqual(resolve_model_name(orphan), '')

        full = _make_usage_record()
        full.ai_model_provider = self.ai_model_provider
        full.save(update_fields=['ai_model_provider'])
        full.refresh_from_db()
        self.assertEqual(resolve_model_name(full), 'test-model')

    # --- tool call summary ------------------------------------------------

    def test_build_tool_calls_summary_empty_and_populated(self):
        """Assert ToolCall rows collapse to {tool_name, success, target}."""
        self.assertEqual(build_tool_calls_summary(self.turn), [])

        ToolCall.objects.create(
            turn=self.turn,
            tool=self.tool,
            arguments=json.dumps({'target': 'foo.py'}),
            call_id='call_ok',
            status_id=ReasoningStatusID.COMPLETED,
        )
        ToolCall.objects.create(
            turn=self.turn,
            tool=self.tool,
            arguments='{}',
            call_id='call_err',
            status_id=ReasoningStatusID.ERROR,
        )

        summary = build_tool_calls_summary(self.turn)
        self.assertEqual(len(summary), 2)
        by_id = {s['target']: s for s in summary}
        self.assertIn('foo.py', by_id)
        self.assertEqual(by_id['foo.py']['success'], True)
        self.assertEqual(by_id['foo.py']['tool_name'], 'test_tool')
        # The error row has no target.
        error_row = [s for s in summary if s['target'] == ''][0]
        self.assertEqual(error_row['success'], False)

    # --- engram ids -------------------------------------------------------

    def test_build_engram_ids_unfiltered(self):
        """Assert both active and inactive engrams appear in the list."""
        active = Engram.objects.create(
            name='mem-active', description='active mem', is_active=True
        )
        inactive = Engram.objects.create(
            name='mem-retired', description='retired mem', is_active=False
        )
        active.source_turns.add(self.turn)
        inactive.source_turns.add(self.turn)

        ids = set(build_engram_ids(self.turn))
        self.assertEqual(ids, {str(active.id), str(inactive.id)})

    # --- idempotence ------------------------------------------------------

    def test_build_and_save_digest_idempotent(self):
        """Assert calling the builder twice leaves one row and bumps modified."""
        usage = _make_usage_record(
            response_payload={'role': 'assistant', 'content': 'Hi'}
        )
        self.turn.model_usage_record = usage
        self.turn.save(update_fields=['model_usage_record'])

        first = build_and_save_digest(self.turn)
        created_at = first.created
        second = build_and_save_digest(self.turn)

        self.assertEqual(
            ReasoningTurnDigest.objects.filter(turn=self.turn).count(), 1
        )
        self.assertEqual(first.pk, second.pk)
        self.assertGreaterEqual(second.modified, created_at)

    # --- push/pull shape symmetry -----------------------------------------

    def test_serializer_matches_vesicle(self):
        """Assert DigestSerializer output is dict-equal to the vesicle."""
        usage = _make_usage_record(
            response_payload={'role': 'assistant', 'content': 'Symmetry'},
            input_tokens=3,
            output_tokens=5,
        )
        usage.ai_model_provider = self.ai_model_provider
        usage.save(update_fields=['ai_model_provider'])
        self.turn.model_usage_record = usage
        self.turn.save(update_fields=['model_usage_record'])

        digest = ReasoningTurnDigest.objects.get(turn=self.turn)
        vesicle = digest_to_vesicle(digest)
        serialized = DigestSerializer(digest).data
        self.assertEqual(dict(serialized), vesicle)

    # --- payload assembly round-trip --------------------------------------

    def test_build_digest_payload_defaults_when_usage_is_none(self):
        """Assert payload kwargs degrade gracefully without a usage record."""
        payload = build_digest_payload(self.turn)
        self.assertEqual(payload['session_id'], self.session.id)
        self.assertEqual(payload['turn_number'], 1)
        self.assertEqual(payload['model_name'], '')
        self.assertEqual(payload['tokens_in'], 0)
        self.assertEqual(payload['tokens_out'], 0)
        self.assertEqual(payload['excerpt'], '')
        self.assertEqual(payload['tool_calls_summary'], [])
        self.assertEqual(payload['engram_ids'], [])
