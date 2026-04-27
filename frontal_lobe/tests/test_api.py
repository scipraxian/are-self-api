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
from hippocampus.models import Engram
from parietal_lobe.models import ToolCall, ToolDefinition
from frontal_lobe import constants
from frontal_lobe.models import (
    ReasoningSession,
    ReasoningStatus,
    ReasoningTurn,
)


class ReasoningAPITest(TestCase):
    # Loads CANONICAL + INCUBATOR NeuralModifier rows so any
    # ToolDefinition.objects.create() call defaulting genome to
    # NeuralModifier.INCUBATOR has the FK target present in the test DB.
    fixtures = ['neuroplasticity/fixtures/genetic_immutables.json']

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

        from hypothalamus.models import AIModel, LLMProvider, AIModelProvider, AIModelProviderUsageRecord

        self.model = AIModel.objects.create(name='test-model', context_length=4096)
        self.provider = LLMProvider.objects.create(key='test-provider', base_url='http://test.com')
        self.ai_model_provider = AIModelProvider.objects.create(
            ai_model=self.model,
            provider=self.provider,
            provider_unique_model_id='test-model-id'
        )

        self.usage_record = AIModelProviderUsageRecord.objects.create(
            ai_model_provider=self.ai_model_provider,
            ai_model=self.model,
            request_payload={'test': 'data'},
            response_payload={'content': 'Thinking 1'},
            input_tokens=10,
            output_tokens=20
        )

        self.turn = ReasoningTurn.objects.create(
            session=self.session,
            turn_number=1,
            model_usage_record=self.usage_record,
            status=self.status_active,
        )

        self.tool = ToolDefinition.objects.create(name='TestTool')
        self.tool_call = ToolCall.objects.create(
            turn=self.turn, tool=self.tool, arguments='{}', call_id='call_123'
        )

        self.engram = Engram.objects.create(
            description='Test Engram', relevance_score=0.9
        )
        self.engram.sessions.add(self.session)
        self.engram.source_turns.add(self.turn)

    def test_graph_data_returns_digest_list(self):
        """Assert graph_data returns a list of digests matching the vesicle shape."""
        url = reverse('reasoningsession-graph-data', args=[self.session.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # New shape: flat list of ReasoningTurnDigest rows written by the
        # post_save signal. The setUp turn has a usage record, so exactly
        # one digest exists.
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 1)
        digest = response.data[0]
        self.assertEqual(digest['turn_id'], str(self.turn.id))
        self.assertEqual(digest['session_id'], str(self.session.id))
        self.assertEqual(digest['turn_number'], 1)

    def test_graph_data_since_turn_number_filters(self):
        """Assert since_turn_number=N filters out digests with turn_number <= N."""
        url = reverse('reasoningsession-graph-data', args=[self.session.id])
        response = self.client.get(url, {'since_turn_number': 1})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_graph_data_rejects_non_integer_since(self):
        """Assert a non-integer since_turn_number returns 400."""
        url = reverse('reasoningsession-graph-data', args=[self.session.id])
        response = self.client.get(url, {'since_turn_number': 'not-a-number'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
