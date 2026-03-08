from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from central_nervous_system.models import (
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
)
from hippocampus.models import TalosEngram
from parietal_lobe.models import ToolCall, ToolDefinition
from frontal_lobe import constants
from frontal_lobe.models import (
    ReasoningGoal,
    ReasoningSession,
    ReasoningStatus,
    ReasoningTurn,
)


class ReasoningAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.status_active = ReasoningStatus.objects.create(
            id=ReasoningStatus.ACTIVE, name='Active'
        )
        self.status_pending = ReasoningStatus.objects.create(
            id=ReasoningStatus.PENDING, name='Pending'
        )

        spike_status, _ = SpikeStatus.objects.get_or_create(
            id=1, defaults={'name': 'Created'}
        )
        spike_train_status, _ = SpikeTrainStatus.objects.get_or_create(
            id=1, defaults={'name': 'Created'}
        )

        self.spike_train = SpikeTrain.objects.create(status=spike_train_status)
        self.spike = Spike.objects.create(
            spike_train=self.spike_train, status=spike_status
        )

        self.session = ReasoningSession.objects.create(
            spike=self.spike, status=self.status_active
        )
        self.goal = ReasoningGoal.objects.create(
            session=self.session,
            status=self.status_active,
            rendered_goal='Sub Goal 1',
        )

        self.turn = ReasoningTurn.objects.create(
            session=self.session,
            turn_number=1,
            request_payload={'test': 'data'},
            thought_process='Thinking 1',
            status=self.status_active,
        )
        self.turn.turn_goals.add(self.goal)

        self.tool = ToolDefinition.objects.create(name='TestTool')
        self.tool_call = ToolCall.objects.create(
            turn=self.turn, tool=self.tool, arguments='{}', call_id='call_123'
        )

        self.engram = TalosEngram.objects.create(
            description='Test Engram', relevance_score=0.9
        )
        self.engram.sessions.add(self.session)
        self.engram.source_turns.add(self.turn)

    def test_graph_data_api(self):
        """Verifies pure JSON tree serialization outputs exact keys."""
        url = reverse('reasoningsession-graph-data', args=[self.session.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        # --- FIX: Check for the native REST keys instead of the old D3 keys ---
        self.assertIn('goals', data)
        self.assertIn('turns', data)
        self.assertIn('engrams', data)
        self.assertIn('status_name', data)
