import json
from django.test import TestCase, Client
from django.urls import reverse
from talos_reasoning.models import ReasoningSession, ReasoningTurn, ReasoningGoal, ReasoningStatus, ReasoningStatusID
from talos_hippocampus.models import TalosEngram
from talos_parietal.models import ToolDefinition, ToolCall


class LcarsApiTest(TestCase):

    def setUp(self):
        self.client = Client()

        # Create Statuses
        self.status = ReasoningStatus.objects.create(
            id=ReasoningStatusID.ACTIVE, name="Active")
        ReasoningStatus.objects.create(id=ReasoningStatusID.PENDING,
                                       name="Pending")

        # Create Session
        self.session = ReasoningSession.objects.create(goal="Test Goal",
                                                       status=self.status)

        # Create Goal
        self.goal = ReasoningGoal.objects.create(session=self.session,
                                                 status=self.status,
                                                 rendered_goal="Sub Goal 1")

        # Create Turn
        self.turn = ReasoningTurn.objects.create(
            session=self.session,
            active_goal=self.goal,
            turn_number=1,
            input_context_snapshot="Input 1",
            thought_process="Thinking 1",
            status=self.status)

        # Create Tool & Call
        self.tool = ToolDefinition.objects.create(name="TestTool")
        self.tool_call = ToolCall.objects.create(turn=self.turn,
                                                 tool=self.tool,
                                                 arguments="{}",
                                                 call_id="call_123")

        # Create Engram
        self.engram = TalosEngram.objects.create(description="Test Engram",
                                                 relevance_score=0.9)
        self.engram.sessions.add(self.session)
        self.engram.source_turns.add(self.turn)

    def test_lcars_view(self):
        url = reverse('talos_reasoning:lcars_view', args=[self.session.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'talos_reasoning/lcars_view.html')

    def test_graph_data_api(self):
        url = reverse('talos_reasoning:session_graph_data',
                      args=[self.session.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)

        # Verify Structure
        self.assertIn('nodes', data)
        self.assertIn('links', data)
        self.assertIn('session', data)

        # Verify content
        self.assertEqual(data['session']['id'], str(self.session.id))
        self.assertTrue(len(data['nodes']) >= 3)  # Turn + Engram + Tool

        # Check node types
        types = [n['type'] for n in data['nodes']]
        self.assertIn('turn', types)
        self.assertIn('engram', types)
        self.assertIn('tool', types)

        # Check links
        # Should have link from Turn -> Engram and Turn -> Tool
        link_types = [l['type'] for l in data['links']]
        self.assertIn('created_in', link_types)
        self.assertIn('uses_tool', link_types)
