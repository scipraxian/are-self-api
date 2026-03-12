import json

import pytest
from asgiref.sync import sync_to_async

from common.tests.common_test_case import CommonFixturesAPITestCase
from frontal_lobe.constants import FrontalLobeConstants
from frontal_lobe.frontal_lobe import FrontalLobe
from frontal_lobe.models import (
    ReasoningGoal,
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)
from identity.models import Identity, IdentityDisc, IdentityType
from parietal_lobe.models import ToolCall, ToolDefinition


class LivingChatroomTest(CommonFixturesAPITestCase):
    """
    Regression tests for the Living Chatroom payload builder.
    """

    def setUp(self):
        super().setUp()

        # Minimal session + identity wiring so FrontalLobe can resolve prompts
        self.session = ReasoningSession.objects.create(
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=10,
            current_focus=5,
            total_xp=0,
        )

        pm_type, _ = IdentityType.objects.get_or_create(
            id=IdentityType.PM, defaults={'name': 'PM'}
        )
        self.identity = Identity.objects.create(
            name='Test PM',
            identity_type=pm_type,
            system_prompt_template='You are a PM.',
        )
        self.identity_disc = IdentityDisc.objects.create(
            identity=self.identity,
            name='PM [Mk.1]',
        )
        self.session.identity_disc = self.identity_disc
        self.session.save(update_fields=['identity_disc'])

        self.status_goal_active = ReasoningStatusID.ACTIVE
        self.goal = ReasoningGoal.objects.create(
            session=self.session,
            status_id=self.status_goal_active,
            rendered_goal='Test goal',
        )

        # Simple log collector instead of hitting the DB in tests
        self.log_messages = []

        async def log_cb(msg: str):
            self.log_messages.append(msg)

        # Fake spike object with minimal interface for FrontalLobe
        class DummySpike:
            def __init__(self):
                self.id = 'dummy-spike'
                self.application_log = ''

            def save(self, update_fields=None):
                pass

        self.spike = DummySpike()
        self.lobe = FrontalLobe(self.spike)
        self.lobe.session = self.session
        self.lobe.current_goal = self.goal
        self.lobe._log_live = log_cb

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_history_messages_use_parsed_tool_arguments(self):
        """
        Ensures _build_history_messages emits tool_calls with JSON objects
        for arguments instead of raw JSON strings, avoiding Ollama 400 errors.
        """
        # Turn 1: completed with a tool call whose arguments are stored as JSON string
        turn1 = await sync_to_async(ReasoningTurn.objects.create)(
            session=self.session,
            turn_number=1,
            status_id=ReasoningStatusID.COMPLETED,
            request_payload={
                'messages': [
                    {
                        'role': FrontalLobeConstants.ROLE_USER,
                        'content': 'User ctx',
                    }
                ]
            },
            thought_process='THOUGHT: test',
        )

        tool_def = await sync_to_async(ToolDefinition.objects.create)(
            name='mcp_test_tool',
            is_async=True,
        )
        await sync_to_async(
            ToolCall.objects.create
        )(
            turn=turn1,
            tool=tool_def,
            arguments='{"foo": "bar"}',
            result_payload='OK',
        )

        # Turn 2: active turn that looks back at turn 1
        turn2 = await sync_to_async(ReasoningTurn.objects.create)(
            session=self.session,
            turn_number=2,
            status_id=ReasoningStatusID.ACTIVE,
        )

        history_msgs = await self.lobe._build_history_messages(turn2)

        # Find the assistant message with tool_calls
        assistant_with_tools = next(
            (
                m
                for m in history_msgs
                if m.get('role') == FrontalLobeConstants.ROLE_ASSISTANT
                and m.get('tool_calls')
            ),
            None,
        )
        assert assistant_with_tools is not None
        tool_calls = assistant_with_tools['tool_calls']
        assert isinstance(tool_calls, list) and len(tool_calls) == 1

        func = tool_calls[0]['function']
        # Critical: arguments must be a dict, not a raw JSON string
        assert isinstance(func['arguments'], dict)
        assert func['arguments'] == {'foo': 'bar'}

        # Entire payload should be JSON-serializable without errors
        payload = {'messages': history_msgs}
        json.dumps(payload)

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_full_turn_payload_is_valid_json(self):
        """
        Builds a complete Living Chatroom payload and verifies it is
        JSON-serializable and structurally coherent.
        """
        # Seed one completed prior turn to populate history
        prior_turn = await sync_to_async(ReasoningTurn.objects.create)(
            session=self.session,
            turn_number=1,
            status_id=ReasoningStatusID.COMPLETED,
            request_payload={
                'messages': [
                    {
                        'role': FrontalLobeConstants.ROLE_USER,
                        'content': 'Prev user ctx',
                    }
                ]
            },
            thought_process='Prev thought',
        )

        # Current turn
        current_turn = await sync_to_async(ReasoningTurn.objects.create)(
            session=self.session,
            turn_number=2,
            status_id=ReasoningStatusID.ACTIVE,
            last_turn=prior_turn,
        )

        messages = await self.lobe._build_turn_payload(current_turn)

        # Basic shape assertions
        assert isinstance(messages, list)
        assert len(messages) > 0
        assert messages[0]['role'] == FrontalLobeConstants.ROLE_SYSTEM

        # Must contain at least one final sensory/user message
        assert any(
            m.get('role') == FrontalLobeConstants.ROLE_USER
            and 'YOUR MOVE' in (m.get('content') or '')
            for m in messages
        )

        # The entire request payload we would send to Ollama must be valid JSON
        payload = {'messages': messages}
        json.dumps(payload)

