import os
from unittest.mock import MagicMock, patch

from rest_framework import status

from common.tests.common_test_case import CommonFixturesAPITestCase
from hypothalamus.api import _enrich_from_parser
from hypothalamus.parsing_tools.llm_provider_parser.model_semantic_parser import (
    parse_model_string,
)
from hypothalamus.models import (
    AIMode,
    AIModel,
    AIModelCreator,
    AIModelDescription,
    AIModelFamily,
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

    def test_trip_circuit_breaker_increments_counters(self):
        """Assert trip_circuit_breaker increments counter and sets cooldown."""
        self.model_provider.rate_limit_counter = 0
        self.model_provider.rate_limit_total_failures = 0
        self.model_provider.save()

        self.model_provider.trip_circuit_breaker()
        self.model_provider.refresh_from_db()

        assert self.model_provider.rate_limit_counter == 1
        assert self.model_provider.rate_limit_total_failures == 1
        assert self.model_provider.rate_limited_on is not None
        assert self.model_provider.rate_limit_reset_time is not None
        # First trip: 2^0 * 60s = 60s cooldown
        cooldown = (
            self.model_provider.rate_limit_reset_time
            - self.model_provider.rate_limited_on
        )
        assert cooldown.total_seconds() == 60

    def test_trip_circuit_breaker_exponential_backoff(self):
        """Assert cooldown doubles with each consecutive trip."""
        self.model_provider.rate_limit_counter = 0
        self.model_provider.rate_limit_total_failures = 0
        self.model_provider.save()

        # Trip 3 times, verify escalation
        expected_seconds = [60, 120, 240]
        for i, expected in enumerate(expected_seconds):
            self.model_provider.trip_circuit_breaker()
            self.model_provider.refresh_from_db()
            cooldown = (
                self.model_provider.rate_limit_reset_time
                - self.model_provider.rate_limited_on
            )
            assert cooldown.total_seconds() == expected, (
                f'Trip {i + 1}: expected {expected}s, got {cooldown.total_seconds()}s'
            )

    def test_trip_circuit_breaker_caps_at_max_cooldown(self):
        """Assert cooldown never exceeds MAX_CIRCUIT_BREAKER_COOLDOWN (5 min)."""
        from hypothalamus.models import AIModelProviderRateLimitMixin

        max_seconds = AIModelProviderRateLimitMixin.MAX_CIRCUIT_BREAKER_COOLDOWN.total_seconds()

        # Simulate many prior failures
        self.model_provider.rate_limit_counter = 50
        self.model_provider.rate_limit_total_failures = 50
        self.model_provider.save()

        self.model_provider.trip_circuit_breaker()
        self.model_provider.refresh_from_db()

        cooldown = (
            self.model_provider.rate_limit_reset_time
            - self.model_provider.rate_limited_on
        )
        assert cooldown.total_seconds() <= max_seconds, (
            f'Cooldown {cooldown.total_seconds()}s exceeded max {max_seconds}s'
        )

    def test_trip_circuit_breaker_no_overflow_at_extreme_counter(self):
        """Assert no OverflowError even with an absurd counter value."""
        self.model_provider.rate_limit_counter = 10000
        self.model_provider.save()

        # This used to raise OverflowError: date value out of range
        self.model_provider.trip_circuit_breaker()
        self.model_provider.refresh_from_db()

        assert self.model_provider.rate_limit_reset_time is not None

    def test_trip_resource_cooldown_flat_and_no_counter_change(self):
        """Assert resource cooldown is fixed 60s and doesn't touch the counter."""
        self.model_provider.rate_limit_counter = 0
        self.model_provider.rate_limit_total_failures = 0
        self.model_provider.save()

        # Trip it multiple times — cooldown should stay flat
        for _ in range(5):
            self.model_provider.trip_resource_cooldown()
            self.model_provider.refresh_from_db()

            cooldown = (
                self.model_provider.rate_limit_reset_time
                - self.model_provider.rate_limited_on
            )
            assert cooldown.total_seconds() == 60

        # Counter must not have moved
        assert self.model_provider.rate_limit_counter == 0
        assert self.model_provider.rate_limit_total_failures == 0

    def test_resource_cooldown_does_not_affect_existing_counter(self):
        """Assert resource cooldown doesn't corrupt an in-progress backoff."""
        # Simulate a provider already at counter=3 from real failures
        self.model_provider.rate_limit_counter = 3
        self.model_provider.rate_limit_total_failures = 3
        self.model_provider.save()

        self.model_provider.trip_resource_cooldown()
        self.model_provider.refresh_from_db()

        # Counter untouched — next real failure still uses counter=3
        assert self.model_provider.rate_limit_counter == 3
        assert self.model_provider.rate_limit_total_failures == 3

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


class TestEnrichFromParser(CommonFixturesAPITestCase):

    def test_enrich_creates_missing_family(self):
        """Assert parser-identified family that isn't in fixtures gets created."""
        model = AIModel.objects.create(
            name='test-model', context_length=4096
        )
        _enrich_from_parser(model, parse_model_string('ollama/llama3.2:3b'))
        model.refresh_from_db()
        assert model.family is not None
        assert model.family.name == 'Llama'

    def test_enrich_creates_subfamily_with_parent(self):
        """Assert Qwen Coder gets parent link to Qwen."""
        model = AIModel.objects.create(
            name='test-qwen-coder', context_length=4096
        )
        _enrich_from_parser(model, parse_model_string('ollama/qwen2.5-coder:7b'))
        model.refresh_from_db()
        assert model.family is not None
        assert model.family.name == 'Qwen Coder'
        assert model.family.parent is not None
        assert model.family.parent.name == 'Qwen'

    def test_enrich_creates_missing_creator(self):
        """Assert parser-identified creator gets created."""
        model = AIModel.objects.create(
            name='test-model', context_length=4096
        )
        _enrich_from_parser(model, parse_model_string('ollama/gemma3:4b'))
        model.refresh_from_db()
        assert model.creator is not None
        assert model.creator.name == 'Google'

    def test_enrich_does_not_overwrite_existing(self):
        """Assert existing family is not replaced by parser."""
        existing_family = AIModelFamily.objects.create(
            name='Custom', slug='custom'
        )
        model = AIModel.objects.create(
            name='test', context_length=4096, family=existing_family
        )
        _enrich_from_parser(model, parse_model_string('ollama/llama3:8b'))
        model.refresh_from_db()
        assert model.family.name == 'Custom'

    def test_enrich_parameter_size_float(self):
        """Assert parameter_size is parsed to float."""
        model = AIModel.objects.create(
            name='test', context_length=4096
        )
        _enrich_from_parser(model, parse_model_string('ollama/llama3:8b'))
        model.refresh_from_db()
        assert model.parameter_size == 8.0
