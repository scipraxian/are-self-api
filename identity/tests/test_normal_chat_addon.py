from common.tests.common_test_case import CommonFixturesAPITestCase
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)
from hypothalamus.models import (
    AIModel,
    AIModelProvider,
    AIModelProviderUsageRecord,
    LLMProvider,
)
from identity.addons.normal_chat_addon import normal_chat_addon
from parietal_lobe.models import ToolCall, ToolDefinition


class NormalChatAddonTest(CommonFixturesAPITestCase):
    """Tests for the normal_chat_addon history reconstruction.

    Normal Chat is the no-eviction, no-decay sibling of river_of_six:
    the entire prior-turn history is replayed verbatim, in chronological
    order, using the same atomic sources (<<h>>-tagged user messages,
    response_payload assistant, ToolCall DB records).
    """

    def setUp(self):
        super().setUp()
        self.model = AIModel.objects.create(
            name='test-model', context_length=131072
        )
        self.provider = LLMProvider.objects.create(
            key='test-provider', base_url='http://test.com'
        )
        self.ai_model_provider = AIModelProvider.objects.create(
            ai_model=self.model,
            provider=self.provider,
            provider_unique_model_id='test/test-model',
        )
        self.session = ReasoningSession.objects.create(total_xp=0)
        self.tool_def = ToolDefinition.objects.create(
            name='mcp_get_ticket',
            description='Fetches a ticket.',
        )

    def _make_usage_record(
        self,
        request_payload=None,
        response_payload=None,
    ) -> AIModelProviderUsageRecord:
        return AIModelProviderUsageRecord.objects.create(
            ai_model_provider=self.ai_model_provider,
            ai_model=self.model,
            request_payload=request_payload or [],
            response_payload=response_payload or {},
        )

    def _make_response_payload(self, content='', tool_calls=None):
        """Build an OpenAI-style response_payload."""
        message = {'role': 'assistant', 'content': content}
        if tool_calls:
            message['tool_calls'] = tool_calls
        return {
            'choices': [{'message': message}],
        }

    def _make_turn(
        self, turn_number, usage_record, last_turn=None
    ) -> ReasoningTurn:
        return ReasoningTurn.objects.create(
            session=self.session,
            turn_number=turn_number,
            model_usage_record=usage_record,
            last_turn=last_turn,
            status_id=ReasoningStatusID.COMPLETED,
        )

    def _make_tool_call(
        self, turn, call_id='call_abc', result='{"key": "value"}'
    ) -> ToolCall:
        return ToolCall.objects.create(
            turn=turn,
            tool=self.tool_def,
            arguments='{"ticket_id": 1}',
            result_payload=result,
            call_id=call_id,
            status_id=ReasoningStatusID.COMPLETED,
        )

    def test_empty_session_returns_empty(self):
        """Assert normal_chat_addon returns empty list for first turn."""
        usage = self._make_usage_record()
        turn = self._make_turn(1, usage)
        self.assertEqual(normal_chat_addon(turn), [])

    def test_none_turn_returns_empty(self):
        """Assert passing None returns empty list."""
        self.assertEqual(normal_chat_addon(None), [])

    def test_single_prior_turn_with_human_message(self):
        """Assert single prior turn replays human msg + assistant + tool."""
        response = self._make_response_payload(
            content='Fetching ticket.',
            tool_calls=[{
                'id': 'call_1',
                'type': 'function',
                'function': {
                    'name': 'mcp_get_ticket',
                    'arguments': '{"ticket_id": 1}',
                },
            }],
        )
        usage1 = self._make_usage_record(
            request_payload=[
                {'role': 'user', 'content': '<<h>>\nGet ticket 1'},
            ],
            response_payload=response,
        )
        turn1 = self._make_turn(1, usage1)
        self._make_tool_call(turn1, call_id='call_1', result='{"title": "Bug"}')

        usage2 = self._make_usage_record()
        turn2 = self._make_turn(2, usage2, last_turn=turn1)

        result = normal_chat_addon(turn2)

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['role'], 'user')
        self.assertTrue(result[0]['content'].startswith('<<h>>'))
        self.assertEqual(result[1]['role'], 'assistant')
        self.assertIn('tool_calls', result[1])
        self.assertEqual(result[2]['role'], 'tool')
        self.assertEqual(result[2]['tool_call_id'], 'call_1')

    def test_all_prior_turns_replayed_in_order(self):
        """Assert EVERY prior turn is replayed in chronological order.

        This is the regression test for the single-turn bug: before the fix,
        `.first()` on the prior-turns queryset meant only the most recent
        prior turn was reconstructed, no matter how deep the session ran.
        """
        turns = []
        for i in range(1, 11):  # 10 prior turns
            response = self._make_response_payload(
                content=f'Assistant turn {i}.'
            )
            usage = self._make_usage_record(
                request_payload=[
                    {'role': 'user', 'content': f'<<h>>\nhuman turn {i}'},
                ],
                response_payload=response,
            )
            last = turns[-1] if turns else None
            turns.append(self._make_turn(i, usage, last_turn=last))

        usage_current = self._make_usage_record()
        current = self._make_turn(11, usage_current, last_turn=turns[-1])

        result = normal_chat_addon(current)

        user_msgs = [m for m in result if m.get('role') == 'user']
        assistant_msgs = [m for m in result if m.get('role') == 'assistant']

        self.assertEqual(len(user_msgs), 10)
        self.assertEqual(len(assistant_msgs), 10)

        # Chronological order check: turn 1 first, turn 10 last.
        for i, msg in enumerate(user_msgs, start=1):
            self.assertIn(f'human turn {i}', msg['content'])
        for i, msg in enumerate(assistant_msgs, start=1):
            self.assertIn(f'Assistant turn {i}', msg['content'])

    def test_no_eviction_on_old_tool_results(self):
        """Assert tool results from the deepest turns are retained verbatim.

        Normal Chat is the no-eviction variant — tool results and
        tool_calls must survive past river_of_six's age>=4 eviction
        threshold (it has none).
        """
        turns = []
        for i in range(1, 11):  # 10 prior turns, each with a tool call
            response = self._make_response_payload(
                content=f'Turn {i}',
                tool_calls=[{
                    'id': f'call_{i}',
                    'type': 'function',
                    'function': {
                        'name': 'mcp_get_ticket',
                        'arguments': f'{{"id": {i}}}',
                    },
                }],
            )
            usage = self._make_usage_record(response_payload=response)
            last = turns[-1] if turns else None
            turn = self._make_turn(i, usage, last_turn=last)
            self._make_tool_call(
                turn, call_id=f'call_{i}', result=f'result_{i}'
            )
            turns.append(turn)

        usage_current = self._make_usage_record()
        current = self._make_turn(11, usage_current, last_turn=turns[-1])

        result = normal_chat_addon(current)

        # Every prior turn keeps its tool_calls on the assistant msg.
        assistant_with_tools = [
            m for m in result
            if m.get('role') == 'assistant' and 'tool_calls' in m
        ]
        self.assertEqual(len(assistant_with_tools), 10)

        # Every tool result is present, none dropped.
        tool_msgs = [m for m in result if m.get('role') == 'tool']
        self.assertEqual(len(tool_msgs), 10)

        # No decay / eviction text should be appended to ANY tool content.
        for msg in tool_msgs:
            self.assertNotIn('L1 Cache decay', msg['content'])
            self.assertNotIn('EVICTION IMMINENT', msg['content'])

    def test_untagged_user_messages_not_replayed(self):
        """Assert only <<h>>-tagged user messages are replayed.

        Untagged user messages in request_payload (e.g. prompt_addon's
        per-turn injection) must be skipped — otherwise they appear twice
        from turn 2 onward. This matches river_of_six's behavior and the
        CLAUDE.md contract for the <<h>> tagging system.
        """
        response = self._make_response_payload(content='On it.')
        usage1 = self._make_usage_record(
            request_payload=[
                {'role': 'system', 'content': 'You are an agent.'},
                {'role': 'user', 'content': 'Parse the spike data for errors.'},
                {'role': 'user', 'content': '<<h>>\nalso check the logs'},
            ],
            response_payload=response,
        )
        turn1 = self._make_turn(1, usage1)

        usage2 = self._make_usage_record()
        turn2 = self._make_turn(2, usage2, last_turn=turn1)

        result = normal_chat_addon(turn2)

        user_msgs = [m for m in result if m.get('role') == 'user']
        self.assertEqual(len(user_msgs), 1)
        self.assertTrue(user_msgs[0]['content'].startswith('<<h>>'))

        contents = ' '.join(m.get('content', '') for m in result)
        self.assertNotIn('Parse the spike data', contents)

    def test_multiple_human_messages_in_one_turn_all_replayed(self):
        """Assert every <<h>>-tagged human message is replayed, not just the last."""
        response = self._make_response_payload(content='Got both.')
        usage1 = self._make_usage_record(
            request_payload=[
                {'role': 'user', 'content': '<<h>>\nfirst'},
                {'role': 'user', 'content': 'addon injection'},
                {'role': 'user', 'content': '<<h>>\nsecond'},
            ],
            response_payload=response,
        )
        turn1 = self._make_turn(1, usage1)

        usage2 = self._make_usage_record()
        turn2 = self._make_turn(2, usage2, last_turn=turn1)

        result = normal_chat_addon(turn2)

        user_msgs = [m for m in result if m.get('role') == 'user']
        self.assertEqual(len(user_msgs), 2)
        self.assertIn('first', user_msgs[0]['content'])
        self.assertIn('second', user_msgs[1]['content'])

        contents = ' '.join(m.get('content', '') for m in result)
        self.assertNotIn('addon injection', contents)

    def test_call_id_fallback_to_pk(self):
        """Assert ToolCalls with empty call_id use call_{pk} as fallback."""
        response = self._make_response_payload(content='Using tool')
        usage1 = self._make_usage_record(response_payload=response)
        turn1 = self._make_turn(1, usage1)
        tc = ToolCall.objects.create(
            turn=turn1,
            tool=self.tool_def,
            arguments='{}',
            result_payload='result',
            call_id='',
            status_id=ReasoningStatusID.COMPLETED,
        )

        usage2 = self._make_usage_record()
        turn2 = self._make_turn(2, usage2, last_turn=turn1)

        result = normal_chat_addon(turn2)

        tool_msgs = [m for m in result if m.get('role') == 'tool']
        self.assertEqual(len(tool_msgs), 1)
        self.assertEqual(tool_msgs[0]['tool_call_id'], f'call_{tc.id}')

    def test_turns_from_other_sessions_ignored(self):
        """Assert only this session's turns are replayed."""
        other_session = ReasoningSession.objects.create(total_xp=0)
        other_usage = self._make_usage_record(
            request_payload=[
                {'role': 'user', 'content': '<<h>>\nother session msg'},
            ],
            response_payload=self._make_response_payload(content='other'),
        )
        ReasoningTurn.objects.create(
            session=other_session,
            turn_number=1,
            model_usage_record=other_usage,
            status_id=ReasoningStatusID.COMPLETED,
        )

        usage1 = self._make_usage_record(
            request_payload=[
                {'role': 'user', 'content': '<<h>>\nmy session msg'},
            ],
            response_payload=self._make_response_payload(content='mine'),
        )
        turn1 = self._make_turn(1, usage1)

        usage2 = self._make_usage_record()
        turn2 = self._make_turn(2, usage2, last_turn=turn1)

        result = normal_chat_addon(turn2)

        contents = ' '.join(m.get('content', '') for m in result)
        self.assertIn('my session msg', contents)
        self.assertNotIn('other session msg', contents)

    def test_turns_without_usage_record_skipped(self):
        """Assert turns with no model_usage_record are excluded from history."""
        usage1 = self._make_usage_record(
            request_payload=[
                {'role': 'user', 'content': '<<h>>\nreal turn'},
            ],
            response_payload=self._make_response_payload(content='real'),
        )
        turn1 = self._make_turn(1, usage1)

        # Turn 2 has no usage record (still pending / never executed)
        ReasoningTurn.objects.create(
            session=self.session,
            turn_number=2,
            model_usage_record=None,
            last_turn=turn1,
            status_id=ReasoningStatusID.ACTIVE,
        )

        usage3 = self._make_usage_record()
        turn3 = self._make_turn(3, usage3)

        result = normal_chat_addon(turn3)

        # Only turn 1's reconstruction should appear (turn 2 has no record).
        user_msgs = [m for m in result if m.get('role') == 'user']
        assistant_msgs = [m for m in result if m.get('role') == 'assistant']
        self.assertEqual(len(user_msgs), 1)
        self.assertEqual(len(assistant_msgs), 1)
        self.assertIn('real turn', user_msgs[0]['content'])

    def test_empty_assistant_with_no_tool_calls_skipped(self):
        """Assert empty assistant messages with no tool_calls are not emitted."""
        # Assistant returned nothing — no content, no tool calls.
        usage1 = self._make_usage_record(
            request_payload=[
                {'role': 'user', 'content': '<<h>>\nhi'},
            ],
            response_payload=self._make_response_payload(content=''),
        )
        turn1 = self._make_turn(1, usage1)

        usage2 = self._make_usage_record()
        turn2 = self._make_turn(2, usage2, last_turn=turn1)

        result = normal_chat_addon(turn2)

        empty_assistants = [
            m for m in result
            if m.get('role') == 'assistant'
            and not m.get('content')
            and 'tool_calls' not in m
        ]
        self.assertEqual(len(empty_assistants), 0)
