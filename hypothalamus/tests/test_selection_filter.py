import os

from common.tests.common_test_case import CommonFixturesAPITestCase
from hypothalamus.hypothalamus import Hypothalamus
from hypothalamus.models import (
    AIMode,
    AIModel,
    AIModelPricing,
    AIModelProvider,
    AIModelProviderUsageRecord,
    AIModelSelectionFilter,
    FailoverStrategy,
    FailoverStrategyStep,
    FailoverType,
    LLMProvider,
)
from identity.models import IdentityDisc

os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'


class TestSelectionFilter(CommonFixturesAPITestCase):
    # We load standard fixtures but avoid the problematic hypothalamus fixture

    def setUp(self):
        super().setUp()
        self.mode_chat, _ = AIMode.objects.get_or_create(name='chat')

        # 1. Setup Providers
        self.provider_ollama, _ = LLMProvider.objects.get_or_create(
            key='ollama', defaults={'name': 'Ollama', 'requires_api_key': False}
        )
        self.provider_ollama.requires_api_key = False
        self.provider_ollama.save()

        self.provider_openrouter, _ = LLMProvider.objects.get_or_create(
            key='openrouter',
            defaults={'name': 'OpenRouter', 'requires_api_key': False},
        )
        self.provider_openrouter.requires_api_key = False
        self.provider_openrouter.save()

        # 2. Setup AIModels
        self.model_llama, _ = AIModel.objects.get_or_create(
            name='Llama 3', defaults={'context_length': 8192}
        )
        self.model_claude, _ = AIModel.objects.get_or_create(
            name='Claude 3.5 Sonnet', defaults={'context_length': 200000}
        )

        # 3. Setup AIModelProviders
        self.ollama_llama, _ = AIModelProvider.objects.get_or_create(
            provider_unique_model_id='ollama/llama3',
            defaults={
                'provider': self.provider_ollama,
                'ai_model': self.model_llama,
                'mode': self.mode_chat,
                'is_enabled': True,
            },
        )
        self.ollama_llama.is_enabled = True
        self.ollama_llama.save()

        self.or_claude, _ = AIModelProvider.objects.get_or_create(
            provider_unique_model_id='openrouter/claude-3-5-sonnet',
            defaults={
                'provider': self.provider_openrouter,
                'ai_model': self.model_claude,
                'mode': self.mode_chat,
                'is_enabled': True,
            },
        )

        # 4. Setup Pricing (required by pick_optimal_model)
        AIModelPricing.objects.get_or_create(
            model_provider=self.ollama_llama,
            is_current=True,
            is_active=True,
            defaults={
                'input_cost_per_token': 0.0,
                'output_cost_per_token': 0.0,
            },
        )
        AIModelPricing.objects.get_or_create(
            model_provider=self.or_claude,
            is_current=True,
            is_active=True,
            defaults={
                'input_cost_per_token': 0.0001,
                'output_cost_per_token': 0.0003,
            },
        )

        # 5. Setup Failover Types
        self.type_local, _ = FailoverType.objects.get_or_create(
            name='local_fallback'
        )
        self.type_vector, _ = FailoverType.objects.get_or_create(
            name='vector_search'
        )
        self.type_family, _ = FailoverType.objects.get_or_create(
            name='family_failover'
        )
        self.type_fail, _ = FailoverType.objects.get_or_create(
            name='strict_fail'
        )

        # 6. Setup Strategy
        self.strategy = FailoverStrategy.objects.create(name='Test Strategy')
        FailoverStrategyStep.objects.create(
            strategy=self.strategy, failover_type=self.type_local, order=0
        )
        FailoverStrategyStep.objects.create(
            strategy=self.strategy, failover_type=self.type_vector, order=1
        )

        # 7. Setup Filter
        self.selection_filter = AIModelSelectionFilter.objects.create(
            name='Test Filter',
            preferred_model=self.or_claude,
            local_failover=self.ollama_llama,
            failover_strategy=self.strategy,
        )

        # 8. Setup Budget
        self.disc = IdentityDisc.objects.first()
        from identity.models import (
            BudgetPeriod,
            IdentityBudget,
            IdentityBudgetAssignment,
        )

        self.period_day, _ = BudgetPeriod.objects.get_or_create(name='Daily')
        self.budget_obj = IdentityBudget.objects.create(
            name='Test Budget',
            period=self.period_day,
            max_input_cost_per_token=1.0,
            max_output_cost_per_token=1.0,
        )
        IdentityBudgetAssignment.objects.create(
            identity_disc=self.disc, budget=self.budget_obj, is_active=True
        )

        self.disc.selection_filter = self.selection_filter
        self.disc.save()

    def test_preferred_model_selected_at_attempt_0(self):
        ledger = AIModelProviderUsageRecord.objects.create(
            identity_disc=self.disc, request_payload={'messages': []}
        )
        success = Hypothalamus.pick_optimal_model(ledger, attempt=0)
        assert success is True
        assert ledger.ai_model_provider == self.or_claude

    def test_local_fallback_selected_at_attempt_1(self):
        ledger = AIModelProviderUsageRecord.objects.create(
            identity_disc=self.disc, request_payload={'messages': []}
        )
        # preferred used at 0, 1 maps to step index 0
        success = Hypothalamus.pick_optimal_model(ledger, attempt=1)
        assert success is True
        assert ledger.ai_model_provider == self.ollama_llama

    def test_vector_search_selected_at_attempt_2(self):
        ledger = AIModelProviderUsageRecord.objects.create(
            identity_disc=self.disc, request_payload={'messages': []}
        )
        # preferred at 0, local at 1, vector at 2
        success = Hypothalamus.pick_optimal_model(ledger, attempt=2)
        assert success is True
        assert ledger.ai_model_provider is not None

    def test_banned_provider_ignored(self):
        # Ban Claude's provider
        self.selection_filter.banned_providers.add(self.provider_openrouter)
        ledger = AIModelProviderUsageRecord.objects.create(
            identity_disc=self.disc, request_payload={'messages': []}
        )
        # Attempt 0 (preferred: Claude) should now fail
        success = Hypothalamus.pick_optimal_model(ledger, attempt=0)
        assert success is False

    def test_required_capabilities_enforced(self):
        from hypothalamus.models import AIModelCapabilities

        # Add a requirement for 'vision'
        cap_vision, _ = AIModelCapabilities.objects.get_or_create(name='vision')
        self.selection_filter.required_capabilities.add(cap_vision)

        # Claue doesn't have vision in this test setup
        ledger = AIModelProviderUsageRecord.objects.create(
            identity_disc=self.disc, request_payload={'messages': []}
        )

        # attempt 0 (preferred: Claude) should fail
        success = Hypothalamus.pick_optimal_model(ledger, attempt=0)
        assert success is False

        # Give vision to Claude
        self.model_claude.capabilities.add(cap_vision)
        success = Hypothalamus.pick_optimal_model(ledger, attempt=0)
        assert success is True
        assert ledger.ai_model_provider == self.or_claude
