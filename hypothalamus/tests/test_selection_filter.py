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

    def test_banned_provider_does_not_block_preferred_model(self):
        """Assert preferred model is honoured at attempt 0 even if its provider is banned."""
        self.selection_filter.banned_providers.add(self.provider_openrouter)
        ledger = AIModelProviderUsageRecord.objects.create(
            identity_disc=self.disc, request_payload={'messages': []}
        )
        success = Hypothalamus.pick_optimal_model(ledger, attempt=0)
        assert success is True
        assert ledger.ai_model_provider == self.or_claude

    def test_required_capabilities_do_not_block_preferred_model(self):
        """Assert preferred model is honoured at attempt 0 regardless of required capabilities."""
        from hypothalamus.models import AIModelCapabilities

        cap_vision, _ = AIModelCapabilities.objects.get_or_create(name='vision')
        self.selection_filter.required_capabilities.add(cap_vision)

        # Neither model has vision, but preferred model still wins
        ledger = AIModelProviderUsageRecord.objects.create(
            identity_disc=self.disc, request_payload={'messages': []}
        )
        success = Hypothalamus.pick_optimal_model(ledger, attempt=0)
        assert success is True
        assert ledger.ai_model_provider == self.or_claude

    def test_preferred_model_bypasses_fc_filter_at_attempt_0(self):
        """Assert preferred model is selected even without function_calling tag (explicit choice override)."""
        from hypothalamus.models import AIModelCapabilities

        cap_fc, _ = AIModelCapabilities.objects.get_or_create(
            name='function_calling'
        )
        # Give function_calling to Llama (local) but NOT to Claude (preferred)
        self.model_llama.capabilities.add(cap_fc)

        ledger = AIModelProviderUsageRecord.objects.create(
            identity_disc=self.disc,
            request_payload={'messages': []},
            tool_payload={'tools': [{'name': 'test_tool'}]},
        )
        success = Hypothalamus.pick_optimal_model(ledger, attempt=0)
        assert success is True
        assert ledger.ai_model_provider == self.or_claude

    def test_empty_strategy_respects_strategy_boundary(self):
        """Assert that a strategy with no steps does not leak into the final fallback."""
        empty_strategy = FailoverStrategy.objects.create(
            name='Empty Strategy'
        )
        self.selection_filter.failover_strategy = empty_strategy
        self.selection_filter.preferred_model = None
        self.selection_filter.save()

        ledger = AIModelProviderUsageRecord.objects.create(
            identity_disc=self.disc, request_payload={'messages': []}
        )
        success = Hypothalamus.pick_optimal_model(ledger, attempt=0)
        assert success is False

    def test_preferred_model_bypasses_fc_filter_even_with_empty_strategy(self):
        """Assert preferred model is selected via eligibility fallback even when strategy has no steps."""
        from hypothalamus.models import AIModelCapabilities

        cap_fc, _ = AIModelCapabilities.objects.get_or_create(
            name='function_calling'
        )
        self.model_llama.capabilities.add(cap_fc)

        # Strategy with no steps (matches production config)
        empty_strategy = FailoverStrategy.objects.create(
            name='Empty Strategy'
        )
        self.selection_filter.failover_strategy = empty_strategy
        self.selection_filter.save()

        ledger = AIModelProviderUsageRecord.objects.create(
            identity_disc=self.disc,
            request_payload={'messages': []},
            tool_payload={'tools': [{'name': 'test_tool'}]},
        )
        # Preferred model bypasses fc filter via eligibility check
        success = Hypothalamus.pick_optimal_model(ledger, attempt=0)
        assert success is True
        assert ledger.ai_model_provider == self.or_claude

    def test_preview_matches_production_with_tools(self):
        """Assert preview_model_selection returns preferred model even when it lacks function_calling tag."""
        from hypothalamus.models import AIModelCapabilities
        from parietal_lobe.models import ToolDefinition

        cap_fc, _ = AIModelCapabilities.objects.get_or_create(
            name='function_calling'
        )
        # Only Llama has function_calling
        self.model_llama.capabilities.add(cap_fc)

        # Give the disc enabled tools so preview derives require_fc=True
        tool_def = ToolDefinition.objects.first()
        if not tool_def:
            tool_def = ToolDefinition.objects.create(
                name='test_tool', description='test'
            )
        self.disc.enabled_tools.add(tool_def)

        # Preferred model (Claude) bypasses fc filter via eligibility
        best = Hypothalamus.preview_model_selection(self.disc)
        assert best is not None
        assert best == self.or_claude

    def test_strict_strategy_still_blocks(self):
        """Assert strict_fail strategy step still returns None (no fallback)."""
        strict_strategy = FailoverStrategy.objects.create(
            name='Strict Strategy'
        )
        FailoverStrategyStep.objects.create(
            strategy=strict_strategy,
            failover_type=self.type_fail,
            order=0,
        )
        self.selection_filter.failover_strategy = strict_strategy
        self.selection_filter.preferred_model = None
        self.selection_filter.save()

        ledger = AIModelProviderUsageRecord.objects.create(
            identity_disc=self.disc, request_payload={'messages': []}
        )
        success = Hypothalamus.pick_optimal_model(ledger, attempt=0)
        assert success is False
