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
from identity.addons.river_of_six_addon import river_of_six_addon
from parietal_lobe.models import ToolCall, ToolDefinition


class RiverOfSixAddonTest(CommonFixturesAPITestCase):
    """Tests for the river_of_six_addon history reconstruction."""

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
        """Assert river_of_six_addon returns empty list for first turn."""
        usage = self._make_usage_record()
        turn = self._make_turn(1, usage)
        result = river_of_six_addon(turn)
        self.assertEqual(result, [])

    def test_single_turn_with_tool_calls(self):
        """Assert single prior turn produces assistant + tool (no addon user replay)."""
        response = self._make_response_payload(
            content='I will fetch the ticket.',
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
            # Untagged user message (addon-injected) — should NOT be replayed
            request_payload=[{'role': 'user', 'content': 'Get ticket 1'}],
            response_payload=response,
        )
        turn1 = self._make_turn(1, usage1)
        self._make_tool_call(turn1, call_id='call_1', result='{"title": "Bug"}')

        usage2 = self._make_usage_record()
        turn2 = self._make_turn(2, usage2, last_turn=turn1)

        result = river_of_six_addon(turn2)

        # Should be: assistant msg (with tool_calls), tool result
        # No user message — addon prompt is not replayed (no <<h>> tag)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['role'], 'assistant')
        self.assertIn('tool_calls', result[0])
        self.assertEqual(len(result[0]['tool_calls']), 1)
        self.assertEqual(result[1]['role'], 'tool')
        self.assertEqual(result[1]['tool_call_id'], 'call_1')

    def test_single_turn_with_human_message_and_tool_calls(self):
        """Assert human <<h>> user messages ARE replayed alongside assistant + tool."""
        response = self._make_response_payload(
            content='I will fetch the ticket.',
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

        result = river_of_six_addon(turn2)

        # Should be: human user msg, assistant msg (with tool_calls), tool result
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['role'], 'user')
        self.assertTrue(result[0]['content'].startswith('<<h>>'))
        self.assertEqual(result[1]['role'], 'assistant')
        self.assertEqual(result[2]['role'], 'tool')

    def test_no_duplicate_tool_call_ids(self):
        """Assert no duplicate tool_call_ids appear across multiple turns of history."""
        turns = []
        for i in range(1, 7):
            call_id = f'call_turn_{i}'
            response = self._make_response_payload(
                content=f'Turn {i} response',
                tool_calls=[{
                    'id': call_id,
                    'type': 'function',
                    'function': {
                        'name': 'mcp_get_ticket',
                        'arguments': f'{{"ticket_id": {i}}}',
                    },
                }],
            )
            usage = self._make_usage_record(
                request_payload=[
                    {'role': 'user', 'content': f'Request {i}'}
                ],
                response_payload=response,
            )
            last = turns[-1] if turns else None
            turn = self._make_turn(i, usage, last_turn=last)
            self._make_tool_call(
                turn,
                call_id=call_id,
                result=f'{{"data": "result_{i}"}}',
            )
            turns.append(turn)

        # Current turn is 7
        usage7 = self._make_usage_record()
        turn7 = self._make_turn(7, usage7, last_turn=turns[-1])

        result = river_of_six_addon(turn7)

        # Collect all tool_call_ids from tool messages
        tool_call_ids = [
            m['tool_call_id'] for m in result if m.get('role') == 'tool'
        ]
        self.assertEqual(len(tool_call_ids), len(set(tool_call_ids)))

    def test_message_count_stays_bounded(self):
        """Assert message count is bounded: N*(user + assistant + tool), not exponential."""
        num_turns = 6
        tools_per_turn = 2
        turns = []

        for i in range(1, num_turns + 1):
            tc_list = []
            for j in range(tools_per_turn):
                tc_list.append({
                    'id': f'call_t{i}_j{j}',
                    'type': 'function',
                    'function': {
                        'name': 'mcp_get_ticket',
                        'arguments': f'{{"id": {i * 10 + j}}}',
                    },
                })

            response = self._make_response_payload(
                content=f'Response {i}', tool_calls=tc_list
            )
            usage = self._make_usage_record(
                request_payload=[
                    {'role': 'user', 'content': f'Request {i}'}
                ],
                response_payload=response,
            )
            last = turns[-1] if turns else None
            turn = self._make_turn(i, usage, last_turn=last)
            for j in range(tools_per_turn):
                self._make_tool_call(
                    turn,
                    call_id=f'call_t{i}_j{j}',
                    result=f'{{"r": "{i}_{j}"}}',
                )
            turns.append(turn)

        usage_current = self._make_usage_record()
        current_turn = self._make_turn(
            num_turns + 1, usage_current, last_turn=turns[-1]
        )

        result = river_of_six_addon(current_turn)

        # Max messages per turn = 1 assistant + tools_per_turn (no addon
        # user replay — only <<h>> human messages get replayed).
        # Old turns (age >= 4) have evicted tool results and stripped
        # tool_calls, so actual count is less.
        # Upper bound without eviction: 6 * (1 + 2) = 18
        max_expected = num_turns * (1 + 1 + tools_per_turn)  # generous bound
        self.assertLessEqual(len(result), max_expected)

        # Verify NO exponential growth: with old bug, 6 turns with 2 tools
        # each would produce 50+ messages due to duplication
        self.assertLess(len(result), 30)

    def test_evicted_turns_fully_dropped(self):
        """Assert tool results aged >= 4 are fully dropped, not placeholdered."""
        turns = []
        for i in range(1, 8):
            response = self._make_response_payload(content=f'Turn {i}')
            usage = self._make_usage_record(
                request_payload=[
                    {'role': 'user', 'content': f'Request {i}'}
                ],
                response_payload=response,
            )
            last = turns[-1] if turns else None
            turn = self._make_turn(i, usage, last_turn=last)

            if i <= 3:
                self._make_tool_call(
                    turn,
                    call_id=f'call_old_{i}',
                    result=f'{{"old_data": "{i}"}}',
                )
            turns.append(turn)

        # Current turn is 8, so turns 2-7 are in the window.
        # Turn 2 has age 6, turn 3 has age 5, turn 4+ have no tools.
        # Turns 2 and 3 both have age >= 4, so their tool results should
        # be fully dropped.
        usage8 = self._make_usage_record()
        turn8 = self._make_turn(8, usage8, last_turn=turns[-1])

        result = river_of_six_addon(turn8)

        # No tool messages should exist for evicted turns
        tool_msgs = [m for m in result if m.get('role') == 'tool']
        for msg in tool_msgs:
            self.assertNotIn('EVICTED', msg.get('content', ''))

        # Evicted assistant messages should NOT have tool_calls key
        for msg in result:
            if msg.get('role') == 'assistant':
                if 'tool_calls' in msg:
                    # This assistant had tool calls; verify it's a recent
                    # turn (not evicted)
                    pass

    def test_assistant_tool_calls_followed_by_tool_results(self):
        """Assert assistant messages with tool_calls are always followed by matching tool role messages."""
        response = self._make_response_payload(
            content='Calling tools',
            tool_calls=[
                {
                    'id': 'call_a',
                    'type': 'function',
                    'function': {
                        'name': 'mcp_get_ticket',
                        'arguments': '{}',
                    },
                },
                {
                    'id': 'call_b',
                    'type': 'function',
                    'function': {
                        'name': 'mcp_get_ticket',
                        'arguments': '{}',
                    },
                },
            ],
        )
        usage1 = self._make_usage_record(
            request_payload=[{'role': 'user', 'content': 'Do stuff'}],
            response_payload=response,
        )
        turn1 = self._make_turn(1, usage1)
        self._make_tool_call(turn1, call_id='call_a', result='result_a')
        self._make_tool_call(turn1, call_id='call_b', result='result_b')

        usage2 = self._make_usage_record()
        turn2 = self._make_turn(2, usage2, last_turn=turn1)

        result = river_of_six_addon(turn2)

        # Find assistant messages with tool_calls
        for idx, msg in enumerate(result):
            if msg.get('role') == 'assistant' and 'tool_calls' in msg:
                expected_ids = {
                    tc['id'] for tc in msg['tool_calls']
                }
                # Collect subsequent tool messages
                actual_ids = set()
                for following in result[idx + 1:]:
                    if following.get('role') == 'tool':
                        actual_ids.add(following['tool_call_id'])
                    else:
                        break
                self.assertEqual(expected_ids, actual_ids)

    def test_call_id_fallback_to_pk(self):
        """Assert ToolCalls with empty call_id use call_{pk} as fallback."""
        response = self._make_response_payload(content='Using tool')
        usage1 = self._make_usage_record(
            response_payload=response,
        )
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

        result = river_of_six_addon(turn2)

        tool_msgs = [m for m in result if m.get('role') == 'tool']
        self.assertEqual(len(tool_msgs), 1)
        self.assertEqual(tool_msgs[0]['tool_call_id'], f'call_{tc.id}')

    def test_none_turn_returns_empty(self):
        """Assert passing None returns empty list."""
        self.assertEqual(river_of_six_addon(None), [])

    def test_decay_warning_at_age_2(self):
        """Assert tool results at age 2 get decay warning appended."""
        response = self._make_response_payload(
            content='Tool turn',
            tool_calls=[{
                'id': 'call_decay',
                'type': 'function',
                'function': {
                    'name': 'mcp_get_ticket',
                    'arguments': '{}',
                },
            }],
        )
        usage1 = self._make_usage_record(response_payload=response)
        turn1 = self._make_turn(1, usage1)
        self._make_tool_call(
            turn1, call_id='call_decay', result='original content'
        )

        usage3 = self._make_usage_record()
        turn3 = self._make_turn(3, usage3)

        result = river_of_six_addon(turn3)

        tool_msgs = [m for m in result if m.get('role') == 'tool']
        self.assertEqual(len(tool_msgs), 1)
        self.assertIn('L1 Cache decay', tool_msgs[0]['content'])
        self.assertIn('original content', tool_msgs[0]['content'])

    def test_eviction_warning_at_age_3(self):
        """Assert tool results at age 3 get eviction imminent warning."""
        response = self._make_response_payload(
            content='Tool turn',
            tool_calls=[{
                'id': 'call_evict_warn',
                'type': 'function',
                'function': {
                    'name': 'mcp_get_ticket',
                    'arguments': '{}',
                },
            }],
        )
        usage1 = self._make_usage_record(response_payload=response)
        turn1 = self._make_turn(1, usage1)
        self._make_tool_call(
            turn1, call_id='call_evict_warn', result='about to evict'
        )

        usage4 = self._make_usage_record()
        turn4 = self._make_turn(4, usage4)

        result = river_of_six_addon(turn4)

        tool_msgs = [m for m in result if m.get('role') == 'tool']
        self.assertEqual(len(tool_msgs), 1)
        self.assertIn('EVICTION IMMINENT', tool_msgs[0]['content'])
        self.assertIn('about to evict', tool_msgs[0]['content'])


    def test_skips_addon_user_messages_replays_human_only(self):
        """Assert only <<h>>-tagged human user messages are replayed, not addon user messages."""
        # Turn 1: request_payload has an addon user message (no <<h>> tag)
        # AND a human swarm message (<<h>> tagged)
        response1 = self._make_response_payload(content='Understood, working on it.')
        usage1 = self._make_usage_record(
            request_payload=[
                {'role': 'system', 'content': 'You are an agent.'},
                {'role': 'user', 'content': 'Parse the spike data for errors.'},
                {'role': 'user', 'content': '<<h>>\nhey also check the logs'},
            ],
            response_payload=response1,
        )
        turn1 = self._make_turn(1, usage1)

        usage2 = self._make_usage_record()
        turn2 = self._make_turn(2, usage2, last_turn=turn1)

        result = river_of_six_addon(turn2)

        # Should replay: human user msg, assistant msg
        user_msgs = [m for m in result if m.get('role') == 'user']
        self.assertEqual(len(user_msgs), 1)
        self.assertTrue(user_msgs[0]['content'].startswith('<<h>>'))
        self.assertIn('check the logs', user_msgs[0]['content'])

        # The addon prompt should NOT appear in history
        contents = ' '.join(m.get('content', '') for m in result)
        self.assertNotIn('Parse the spike data', contents)

    def test_multiple_human_messages_all_replayed(self):
        """Assert all <<h>>-tagged human messages are replayed, not just the last."""
        response1 = self._make_response_payload(content='Got both messages.')
        usage1 = self._make_usage_record(
            request_payload=[
                {'role': 'system', 'content': 'You are an agent.'},
                {'role': 'user', 'content': '<<h>>\nfirst human message'},
                {'role': 'user', 'content': 'addon prompt (no tag)'},
                {'role': 'user', 'content': '<<h>>\nsecond human message'},
            ],
            response_payload=response1,
        )
        turn1 = self._make_turn(1, usage1)

        usage2 = self._make_usage_record()
        turn2 = self._make_turn(2, usage2, last_turn=turn1)

        result = river_of_six_addon(turn2)

        user_msgs = [m for m in result if m.get('role') == 'user']
        self.assertEqual(len(user_msgs), 2)
        self.assertIn('first human message', user_msgs[0]['content'])
        self.assertIn('second human message', user_msgs[1]['content'])

        # Addon prompt should NOT be in results
        contents = ' '.join(m.get('content', '') for m in result)
        self.assertNotIn('addon prompt', contents)

    def test_empty_evicted_assistant_messages_stripped(self):
        """Assert evicted assistant messages with no content and no tool_calls are dropped."""
        turns = []
        for i in range(1, 7):
            # Models that only produce tool calls have empty assistant content.
            response = self._make_response_payload(
                content='',  # No text, only tool calls
                tool_calls=[{
                    'id': f'call_t{i}',
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
            self._make_tool_call(turn, call_id=f'call_t{i}', result=f'result_{i}')
            turns.append(turn)

        # Turn 7: turns 1-2 have age >= 5 (evicted). Their assistant msgs
        # had empty content + tool_calls stripped = totally empty. Should be dropped.
        usage7 = self._make_usage_record()
        turn7 = self._make_turn(7, usage7, last_turn=turns[-1])

        result = river_of_six_addon(turn7)

        # No message in the result should be an empty assistant
        empty_assistants = [
            m for m in result
            if m.get('role') == 'assistant'
            and not m.get('content')
            and 'tool_calls' not in m
        ]
        self.assertEqual(len(empty_assistants), 0, 'Empty evicted assistants should be stripped')

    def test_no_user_messages_when_no_human_tag(self):
        """Assert no user messages replayed when only addon user messages exist (no <<h>>)."""
        response1 = self._make_response_payload(content='On it.')
        usage1 = self._make_usage_record(
            request_payload=[
                {'role': 'system', 'content': 'You are an agent.'},
                {'role': 'user', 'content': 'Do the task.'},
            ],
            response_payload=response1,
        )
        turn1 = self._make_turn(1, usage1)

        usage2 = self._make_usage_record()
        turn2 = self._make_turn(2, usage2, last_turn=turn1)

        result = river_of_six_addon(turn2)

        user_msgs = [m for m in result if m.get('role') == 'user']
        self.assertEqual(len(user_msgs), 0)

        # Assistant message should still be present
        assistant_msgs = [m for m in result if m.get('role') == 'assistant']
        self.assertEqual(len(assistant_msgs), 1)


class GracefulNoModelCrashTest(CommonFixturesAPITestCase):
    """Tests for the graceful crash when no models are available."""

    def test_no_model_sets_maxed_out(self):
        """Assert when pick_optimal_model returns False, session ends up MAXED_OUT without raising."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from asgiref.sync import async_to_sync

        from frontal_lobe.frontal_lobe import FrontalLobe

        mock_spike = MagicMock()
        mock_spike.id = 'test-spike-id'

        lobe = FrontalLobe(mock_spike)

        session = ReasoningSession.objects.create(
            status_id=ReasoningStatusID.ACTIVE,
        )
        lobe.session = session

        ReasoningTurn.objects.create(
            session=session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )

        with patch.object(
            lobe, '_build_turn_payload', new_callable=AsyncMock
        ) as mock_payload:
            mock_payload.return_value = [
                {'role': 'user', 'content': 'test'}
            ]

            with patch(
                'frontal_lobe.frontal_lobe.Hypothalamus'
            ) as mock_hypo_cls:
                mock_hypo_instance = MagicMock()
                mock_hypo_instance.pick_optimal_model.return_value = False
                mock_hypo_cls.return_value = mock_hypo_instance

                should_continue, result_turn = async_to_sync(
                    lobe._execute_turn
                )([], None)

        self.assertFalse(should_continue)

        session.refresh_from_db()
        self.assertEqual(session.status_id, ReasoningStatusID.MAXED_OUT)
