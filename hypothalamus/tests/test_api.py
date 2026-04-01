import os
from unittest.mock import MagicMock, patch

from rest_framework import status

from common.tests.common_test_case import CommonFixturesAPITestCase
from hypothalamus.models import (
    AIMode,
    AIModel,
    AIModelPricing,
    AIModelProvider,
    AIModelSelectionFilter,
    FailoverStrategy,
    FailoverStrategyStep,
    FailoverType,
    LLMProvider,
)

os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'


class TestAIModelActions(CommonFixturesAPITestCase):

    def setUp(self):
        super().setUp()
        self.mode_chat, _ = AIMode.objects.get_or_create(name='chat')
        self.provider_ollama, _ = LLMProvider.objects.get_or_create(
            key='ollama',
            defaults={'name': 'Ollama', 'requires_api_key': False},
        )
        self.ai_model, _ = AIModel.objects.get_or_create(
            name='test-model',
            defaults={'context_length': 4096},
        )

    def test_toggle_enabled(self):
        """Assert toggle_enabled flips the AIModel.enabled flag."""
        self.ai_model.enabled = True
        self.ai_model.save(update_fields=['enabled'])

        url = f'/api/v2/ai-models/{self.ai_model.pk}/toggle_enabled/'
        resp = self.test_client.post(url)

        assert resp.status_code == status.HTTP_200_OK
        self.ai_model.refresh_from_db()
        assert self.ai_model.enabled is False

        resp = self.test_client.post(url)
        assert resp.status_code == status.HTTP_200_OK
        self.ai_model.refresh_from_db()
        assert self.ai_model.enabled is True

    @patch('hypothalamus.api.http_requests.post')
    @patch('hypothalamus.api.fire_neurotransmitter')
    def test_pull_success(self, mock_fire, mock_post):
        """Assert pull action creates provider and pricing on success."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        url = f'/api/v2/ai-models/{self.ai_model.pk}/pull/'
        resp = self.test_client.post(url)

        assert resp.status_code == status.HTTP_200_OK
        mock_post.assert_called_once()

        provider = AIModelProvider.objects.get(
            provider_unique_model_id=f'ollama/{self.ai_model.name}'
        )
        assert provider.is_enabled is True

        pricing = AIModelPricing.objects.filter(
            model_provider=provider, is_current=True
        )
        assert pricing.exists()

    @patch('hypothalamus.api.http_requests.post')
    def test_pull_failure_returns_502(self, mock_post):
        """Assert pull action returns 502 when Ollama is unreachable."""
        import requests

        mock_post.side_effect = requests.ConnectionError('refused')

        url = f'/api/v2/ai-models/{self.ai_model.pk}/pull/'
        resp = self.test_client.post(url)

        assert resp.status_code == status.HTTP_502_BAD_GATEWAY

    @patch('hypothalamus.api.http_requests.delete')
    @patch('hypothalamus.api.fire_neurotransmitter')
    def test_remove_success(self, mock_fire, mock_delete):
        """Assert remove action disables the Ollama provider."""
        provider = AIModelProvider.objects.create(
            ai_model=self.ai_model,
            provider=self.provider_ollama,
            provider_unique_model_id=f'ollama/{self.ai_model.name}',
            mode=self.mode_chat,
            is_enabled=True,
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_delete.return_value = mock_response

        url = f'/api/v2/ai-models/{self.ai_model.pk}/remove/'
        resp = self.test_client.post(url)

        assert resp.status_code == status.HTTP_200_OK
        provider.refresh_from_db()
        assert provider.is_enabled is False

    @patch('hypothalamus.api.http_requests.delete')
    def test_remove_failure_returns_502(self, mock_delete):
        """Assert remove action returns 502 when Ollama is unreachable."""
        import requests

        mock_delete.side_effect = requests.ConnectionError('refused')

        url = f'/api/v2/ai-models/{self.ai_model.pk}/remove/'
        resp = self.test_client.post(url)

        assert resp.status_code == status.HTTP_502_BAD_GATEWAY


class TestAIModelProviderActions(CommonFixturesAPITestCase):

    def setUp(self):
        super().setUp()
        self.mode_chat, _ = AIMode.objects.get_or_create(name='chat')
        self.provider_ollama, _ = LLMProvider.objects.get_or_create(
            key='ollama',
            defaults={'name': 'Ollama', 'requires_api_key': False},
        )
        self.ai_model, _ = AIModel.objects.get_or_create(
            name='test-provider-model',
            defaults={'context_length': 4096},
        )
        self.model_provider = AIModelProvider.objects.create(
            ai_model=self.ai_model,
            provider=self.provider_ollama,
            provider_unique_model_id='ollama/test-provider-model',
            mode=self.mode_chat,
            is_enabled=True,
            rate_limit_counter=5,
        )

    def test_reset_circuit_breaker(self):
        """Assert reset_circuit_breaker zeroes the counter."""
        url = f'/api/v2/model-providers/{self.model_provider.pk}/reset_circuit_breaker/'
        resp = self.test_client.post(url)

        assert resp.status_code == status.HTTP_200_OK
        self.model_provider.refresh_from_db()
        assert self.model_provider.rate_limit_counter == 0

    def test_toggle_enabled(self):
        """Assert toggle_enabled flips the is_enabled flag."""
        assert self.model_provider.is_enabled is True

        url = f'/api/v2/model-providers/{self.model_provider.pk}/toggle_enabled/'
        resp = self.test_client.post(url)

        assert resp.status_code == status.HTTP_200_OK
        self.model_provider.refresh_from_db()
        assert self.model_provider.is_enabled is False


class TestFailoverEndpoints(CommonFixturesAPITestCase):

    def setUp(self):
        super().setUp()
        self.type_local = FailoverType.objects.create(
            name='local_fallback'
        )
        self.type_vector = FailoverType.objects.create(
            name='vector_search'
        )
        self.strategy = FailoverStrategy.objects.create(
            name='Test Strategy'
        )
        FailoverStrategyStep.objects.create(
            strategy=self.strategy,
            failover_type=self.type_local,
            order=0,
        )
        FailoverStrategyStep.objects.create(
            strategy=self.strategy,
            failover_type=self.type_vector,
            order=1,
        )

    def test_list_failover_types(self):
        """Assert GET failover-types returns the list."""
        resp = self.test_client.get('/api/v2/failover-types/')
        assert resp.status_code == status.HTTP_200_OK
        names = [item['name'] for item in resp.data]
        assert 'local_fallback' in names
        assert 'vector_search' in names

    def test_list_failover_strategies_with_nested_steps(self):
        """Assert GET failover-strategies returns strategies with nested steps."""
        resp = self.test_client.get('/api/v2/failover-strategies/')
        assert resp.status_code == status.HTTP_200_OK
        strategy_data = next(
            s for s in resp.data if s['name'] == 'Test Strategy'
        )
        assert len(strategy_data['steps']) == 2
        assert strategy_data['steps'][0]['failover_type']['name'] == 'local_fallback'


class TestSelectionFilterEndpoint(CommonFixturesAPITestCase):

    def setUp(self):
        super().setUp()
        self.strategy = FailoverStrategy.objects.create(
            name='Filter Strategy'
        )
        self.selection_filter = AIModelSelectionFilter.objects.create(
            name='Test Filter',
            failover_strategy=self.strategy,
        )

    def test_list_selection_filters(self):
        """Assert GET selection-filters returns filters with nested strategy."""
        resp = self.test_client.get('/api/v2/selection-filters/')
        assert resp.status_code == status.HTTP_200_OK
        filter_data = next(
            f for f in resp.data if f['name'] == 'Test Filter'
        )
        assert filter_data['failover_strategy']['name'] == 'Filter Strategy'
