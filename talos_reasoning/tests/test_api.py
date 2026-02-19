from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from talos_hippocampus.models import TalosEngram
from talos_parietal.models import ToolCall, ToolDefinition
from talos_reasoning import constants
from talos_reasoning.models import (
    ReasoningGoal,
    ReasoningSession,
    ReasoningStatus,
    ReasoningTurn,
)


class ReasoningAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Assuming ReasoningStatus inherits from ID constants via NameMixin modifications
        self.status_active = ReasoningStatus.objects.create(id=ReasoningStatus.ACTIVE, name="Active")
        self.status_pending = ReasoningStatus.objects.create(id=ReasoningStatus.PENDING, name="Pending")

        self.session = ReasoningSession.objects.create(goal="Test Goal", status=self.status_active)
        self.goal = ReasoningGoal.objects.create(session=self.session, status=self.status_active, rendered_goal="Sub Goal 1")

        self.turn = ReasoningTurn.objects.create(
            session=self.session,
            active_goal=self.goal,
            turn_number=1,
            input_context_snapshot="Input 1",
            thought_process="Thinking 1",
            status=self.status_active
        )

        self.tool = ToolDefinition.objects.create(name="TestTool")
        self.tool_call = ToolCall.objects.create(
            turn=self.turn,
            tool=self.tool,
            arguments="{}",
            call_id="call_123"
        )

        self.engram = TalosEngram.objects.create(description="Test Engram", relevance_score=0.9)
        self.engram.sessions.add(self.session)
        self.engram.source_turns.add(self.turn)

    def test_lcars_view(self):
        """Verifies the LCARS wrapper renders correctly through the ViewSet action."""
        url = reverse('reasoningsession-lcars', args=[self.session.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTemplateUsed(response, 'talos_reasoning/lcars_view.html')

    def test_graph_data_api(self):
        """Verifies strict DTO serialization outputs exact keys."""
        url = reverse('reasoningsession-graph-data', args=[self.session.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertIn('nodes', data)
        self.assertIn('links', data)

        # Verify Node Types map exactly to constants
        types = [n['type'] for n in data['nodes']]
        self.assertIn(constants.NODE_TURN, types)
        self.assertIn(constants.NODE_ENGRAM, types)
        self.assertIn(constants.NODE_TOOL, types)

        # Verify Link Types
        link_types = [l['type'] for l in data['links']]
        self.assertIn(constants.LINK_CREATED_IN, link_types)
        self.assertIn(constants.LINK_USES_TOOL, link_types)