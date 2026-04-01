import json
import pytest
from asgiref.sync import sync_to_async

from common.tests.common_test_case import CommonFixturesAPITestCase
from frontal_lobe.constants import FrontalLobeConstants
from frontal_lobe.frontal_lobe import FrontalLobe
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatusID,
    ReasoningTurn,
)
from identity.models import Identity, IdentityDisc, IdentityType
from parietal_lobe.models import ToolCall, ToolDefinition

class LivingChatroomTest(CommonFixturesAPITestCase):
    def setUp(self):
        super().setUp()
        self.session = ReasoningSession.objects.create(
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=10,
            current_focus=5,
            total_xp=0,
        )

        pm_type, _ = IdentityType.objects.get_or_create(id=IdentityType.PM, defaults={'name': 'PM'})
        self.identity_disc = IdentityDisc.objects.create(
            name='PM [Mk.1]',
            identity_type=pm_type,
            system_prompt_template='You are a PM.',
        )
        self.session.identity_disc = self.identity_disc
        self.session.save(update_fields=['identity_disc'])

        self.log_messages = []
        async def log_cb(msg: str):
            self.log_messages.append(msg)

        class DummySpike:
            def __init__(self):
                self.id = 'dummy-spike'
                self.application_log = ''
            def save(self, update_fields=None): pass

        self.spike = DummySpike()
        self.lobe = FrontalLobe(self.spike)
        self.lobe.session = self.session
        self.lobe._log_live = log_cb

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_full_turn_payload(self):
        turn1 = await sync_to_async(ReasoningTurn.objects.create)(
            session=self.session,
            turn_number=1,
            status_id=ReasoningStatusID.COMPLETED,
        )

        current_turn = await sync_to_async(ReasoningTurn.objects.create)(
            session=self.session,
            turn_number=2,
            status_id=ReasoningStatusID.ACTIVE,
            last_turn=turn1,
        )

        messages = await self.lobe._build_turn_payload(current_turn)
        assert isinstance(messages, list)
