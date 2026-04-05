import json
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from common.tests.common_test_case import CommonFixturesAPITestCase
from central_nervous_system.models import (
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
)
from hippocampus.models import Engram
from hypothalamus.models import (
    AIModel,
    AIModelProvider,
    AIModelProviderUsageRecord,
    LLMProvider,
)
from parietal_lobe.models import ToolCall, ToolDefinition
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatus,
    ReasoningTurn,
    SessionConclusion,
)


class NarrativeDumpAPITest(CommonFixturesAPITestCase):
    """Test the narrative_dump endpoint."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()

        # Create status fixtures
        self.status_active = ReasoningStatus.objects.get(
            id=ReasoningStatus.ACTIVE
        )
        self.status_pending = ReasoningStatus.objects.get(
            id=ReasoningStatus.PENDING
        )

        # Create spike fixtures
        spike_status = SpikeStatus.objects.get(id=1)
        spike_train_status = SpikeTrainStatus.objects.get(id=1)

        self.spike_train = SpikeTrain.objects.create(
            status=spike_train_status
        )
        self.spike = Spike.objects.create(
            spike_train=self.spike_train, status=spike_status
        )

        # Create session
        self.session = ReasoningSession.objects.create(
            spike=self.spike, status=self.status_active
        )

        # Create model and provider
        self.model = AIModel.objects.create(
            name='test-model', context_length=4096
        )
        self.provider = LLMProvider.objects.create(
            key='test-provider', base_url='http://test.com'
        )
        self.ai_model_provider = AIModelProvider.objects.create(
            ai_model=self.model,
            provider=self.provider,
            provider_unique_model_id='test-model-id',
        )

        # Create usage records and turns
        self.turns = []
        for turn_num in range(1, 3):
            usage_record = AIModelProviderUsageRecord.objects.create(
                ai_model_provider=self.ai_model_provider,
                ai_model=self.model,
                request_payload=[{'role': 'user', 'content': 'Test input'}],
                response_payload={
                    'role': 'assistant',
                    'content': 'Test output',
                },
                input_tokens=10 * turn_num,
                output_tokens=20 * turn_num,
            )

            turn = ReasoningTurn.objects.create(
                session=self.session,
                turn_number=turn_num,
                model_usage_record=usage_record,
                status=self.status_active,
            )
            self.turns.append(turn)

        # Create tools and tool calls
        self.tool_ticket = ToolDefinition.objects.create(
            name='mcp_ticket'
        )
        self.tool_generic = ToolDefinition.objects.create(
            name='mcp_generic'
        )

        # Tool call 1: successful mcp_ticket
        tc1_args = {
            'action': 'update',
            'field_name': 'perspective',
            'ticket_id': 'ABC123',
        }
        self.tc1 = ToolCall.objects.create(
            turn=self.turns[0],
            tool=self.tool_ticket,
            arguments=json.dumps(tc1_args),
            result_payload=json.dumps({'ok': True}),
            call_id='call_001',
        )

        # Tool call 2: successful mcp_ticket
        tc2_args = {
            'action': 'update',
            'field_name': 'assertions',
            'ticket_id': 'ABC123',
        }
        self.tc2 = ToolCall.objects.create(
            turn=self.turns[0],
            tool=self.tool_ticket,
            arguments=json.dumps(tc2_args),
            result_payload=json.dumps({'ok': True}),
            call_id='call_002',
        )

        # Tool call 3: failed mcp_ticket with validation error
        tc3_args = {
            'action': 'update',
            'field_name': 'status',
            'ticket_id': 'ABC123',
        }
        self.tc3 = ToolCall.objects.create(
            turn=self.turns[1],
            tool=self.tool_ticket,
            arguments=json.dumps(tc3_args),
            result_payload=json.dumps(
                {'ok': False, 'error': 'VALIDATION ERROR: Invalid status'}
            ),
            call_id='call_003',
        )

        # Tool call 4: generic tool with success
        self.tc4 = ToolCall.objects.create(
            turn=self.turns[1],
            tool=self.tool_generic,
            arguments='{}',
            result_payload=json.dumps({'ok': True, 'data': 'result'}),
            call_id='call_004',
        )

        # Create engrams
        self.engram1 = Engram.objects.create(
            name='memory_alpha',
            description='First memory formed',
            relevance_score=0.95,
        )
        self.engram1.sessions.add(self.session)

        self.engram2 = Engram.objects.create(
            name='memory_beta',
            description='Second memory formed',
            relevance_score=0.87,
        )
        self.engram2.sessions.add(self.session)

        # Create session conclusion
        self.conclusion = SessionConclusion.objects.create(
            session=self.session,
            summary='This is a test session summary with conclusions.',
            reasoning_trace='Traced reasoning path',
            outcome_status='SUCCESS',
            recommended_action='Continue with next phase',
            status=self.status_active,
        )

    def test_narrative_dump_returns_200(self):
        """Verify narrative_dump endpoint returns 200 OK."""
        url = reverse('reasoningsession-narrative-dump', args=[self.session.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_narrative_dump_returns_file(self):
        """Verify narrative_dump returns a downloadable file."""
        url = reverse('reasoningsession-narrative-dump', args=[self.session.id])
        response = self.client.post(url)

        # Check Content-Disposition header
        self.assertIn('Content-Disposition', response)
        disposition = response['Content-Disposition']
        self.assertIn('attachment', disposition)
        self.assertIn('session_narrative_', disposition)
        self.assertIn('.log', disposition)

    def test_narrative_dump_contains_header(self):
        """Verify narrative_dump contains SESSION NARRATIVE header."""
        url = reverse('reasoningsession-narrative-dump', args=[self.session.id])
        response = self.client.post(url)
        content = response.content.decode('utf-8')

        self.assertIn('SESSION NARRATIVE', content)
        self.assertIn(str(self.session.id)[:8], content)

    def test_narrative_dump_contains_status_line(self):
        """Verify narrative_dump contains status, turns, duration line."""
        url = reverse('reasoningsession-narrative-dump', args=[self.session.id])
        response = self.client.post(url)
        content = response.content.decode('utf-8')

        # Check for status line
        self.assertIn('Active', content)
        self.assertIn('2 turns', content)

    def test_narrative_dump_contains_summary(self):
        """Verify narrative_dump contains SUMMARY section."""
        url = reverse('reasoningsession-narrative-dump', args=[self.session.id])
        response = self.client.post(url)
        content = response.content.decode('utf-8')

        self.assertIn('SUMMARY', content)
        self.assertIn('This is a test session summary with conclusions.', content)

    def test_narrative_dump_contains_parietal_lobe_activity(self):
        """Verify narrative_dump contains PARIETAL LOBE ACTIVITY section."""
        url = reverse('reasoningsession-narrative-dump', args=[self.session.id])
        response = self.client.post(url)
        content = response.content.decode('utf-8')

        self.assertIn('PARIETAL LOBE ACTIVITY (4 calls)', content)
        self.assertIn('mcp_ticket', content)
        self.assertIn('mcp_generic', content)

    def test_narrative_dump_shows_success_indicators(self):
        """Verify narrative_dump shows ✓ for successful calls."""
        url = reverse('reasoningsession-narrative-dump', args=[self.session.id])
        response = self.client.post(url)
        content = response.content.decode('utf-8')

        # Should have checkmarks for successful calls
        self.assertIn('✓', content)

    def test_narrative_dump_shows_error_indicators(self):
        """Verify narrative_dump shows ✗ for failed calls."""
        url = reverse('reasoningsession-narrative-dump', args=[self.session.id])
        response = self.client.post(url)
        content = response.content.decode('utf-8')

        # Should have X for failed calls
        self.assertIn('✗', content)

    def test_narrative_dump_contains_engrams_section(self):
        """Verify narrative_dump contains ENGRAMS section."""
        url = reverse('reasoningsession-narrative-dump', args=[self.session.id])
        response = self.client.post(url)
        content = response.content.decode('utf-8')

        self.assertIn('ENGRAMS:', content)
        self.assertIn('memory_alpha', content)
        self.assertIn('memory_beta', content)

    def test_narrative_dump_contains_errors_section(self):
        """Verify narrative_dump contains ERRORS section."""
        url = reverse('reasoningsession-narrative-dump', args=[self.session.id])
        response = self.client.post(url)
        content = response.content.decode('utf-8')

        self.assertIn('ERRORS', content)
        self.assertIn('VALIDATION ERROR', content)

    def test_narrative_dump_contains_token_summary(self):
        """Verify narrative_dump contains TOKEN SUMMARY section."""
        url = reverse('reasoningsession-narrative-dump', args=[self.session.id])
        response = self.client.post(url)
        content = response.content.decode('utf-8')

        self.assertIn('TOKEN SUMMARY:', content)
        self.assertIn('Total:', content)
        self.assertIn('in ·', content)
        self.assertIn('out', content)

    def test_narrative_dump_includes_action_field_names(self):
        """Verify narrative_dump extracts and shows action/field_name."""
        url = reverse('reasoningsession-narrative-dump', args=[self.session.id])
        response = self.client.post(url)
        content = response.content.decode('utf-8')

        # mcp_ticket tool calls should show action and field_name
        self.assertIn('update perspective', content)
        self.assertIn('update assertions', content)
        self.assertIn('update status', content)

    def test_narrative_dump_filename_includes_id_prefix(self):
        """Verify filename uses first 8 chars of session ID."""
        url = reverse('reasoningsession-narrative-dump', args=[self.session.id])
        response = self.client.post(url)
        disposition = response['Content-Disposition']

        id_prefix = str(self.session.id)[:8]
        expected_filename = 'session_narrative_%s.log' % id_prefix
        self.assertIn(expected_filename, disposition)

    def test_narrative_dump_no_summary_fallback(self):
        """Verify fallback message when no summary exists."""
        # Create a session without conclusion
        session_no_summary = ReasoningSession.objects.create(
            spike=self.spike, status=self.status_active
        )

        url = reverse('reasoningsession-narrative-dump', args=[session_no_summary.id])
        response = self.client.post(url)
        content = response.content.decode('utf-8')

        self.assertIn('Session ended without summary.', content)

    def test_narrative_dump_empty_engrams(self):
        """Verify 'none formed' when session has no engrams."""
        # Create a session without engrams
        session_no_engrams = ReasoningSession.objects.create(
            spike=self.spike, status=self.status_active
        )

        url = reverse('reasoningsession-narrative-dump', args=[session_no_engrams.id])
        response = self.client.post(url)
        content = response.content.decode('utf-8')

        self.assertIn('ENGRAMS: none formed', content)

    def test_narrative_dump_model_and_provider_info(self):
        """Verify model and provider info are included."""
        url = reverse('reasoningsession-narrative-dump', args=[self.session.id])
        response = self.client.post(url)
        content = response.content.decode('utf-8')

        self.assertIn('Model: test-model', content)
        self.assertIn('test-provider', content)
