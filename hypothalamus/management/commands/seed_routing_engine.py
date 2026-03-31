import logging
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

# Adjust these imports based on where you ultimately placed the models
from hypothalamus.models import (
    AIModelSelectionFilter,
    FailoverStrategy,
    FailoverStrategyStep,
    FailoverType,
)
from identity.models import (  # Assuming you put the budget models here
    BudgetPeriod,
    IdentityBudget,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Seeds initial Routing, Failover, and Financial Governance data.'

    def handle(self, *args, **options):
        self.stdout.write('Booting the Hypothalamus Seeder...')

        with transaction.atomic():
            self._seed_failover_ecosystem()
            self._seed_financial_ecosystem()
            self._seed_selection_filters()

        self.stdout.write(
            self.style.SUCCESS('Successfully seeded the routing engine!')
        )

    def _seed_failover_ecosystem(self):
        self.stdout.write('  -> Seeding Failover Types & Strategies...')

        # 1. Base Failover Types
        type_local, _ = FailoverType.objects.get_or_create(
            name='Local Fallback',
            defaults={
                'description': 'Attempt to route to a verified local Ollama model.'
            },
        )
        type_family, _ = FailoverType.objects.get_or_create(
            name='Family Failover',
            defaults={
                'description': 'Attempt to route to a sibling model in the same family (e.g., Llama 3 8B -> Llama 3 70B).'
            },
        )
        type_vector, _ = FailoverType.objects.get_or_create(
            name='Semantic Vector Search',
            defaults={
                'description': 'Use Hypothalamus pgvector to find the closest conceptual match.'
            },
        )
        type_strict, _ = FailoverType.objects.get_or_create(
            name='Strict Fail',
            defaults={
                'description': 'Halt execution and return a routing error.'
            },
        )

        # 2. Strategies
        strat_standard, _ = FailoverStrategy.objects.get_or_create(
            name='Standard Cloud',
            defaults={
                'description': 'Standard API routing with semantic fallback.'
            },
        )
        strat_local_first, _ = FailoverStrategy.objects.get_or_create(
            name='Local First',
            defaults={
                'description': 'Prioritize free local models before touching the cloud.'
            },
        )
        strat_strict, _ = FailoverStrategy.objects.get_or_create(
            name='Strict Requirement',
            defaults={
                'description': 'Do not deviate from the requested model family.'
            },
        )

        # 3. Wire up the Steps (The actual chains)
        # Standard Cloud: Family -> Vector -> Fail
        FailoverStrategyStep.objects.get_or_create(
            strategy=strat_standard,
            order=1,
            defaults={'failover_type': type_family},
        )
        FailoverStrategyStep.objects.get_or_create(
            strategy=strat_standard,
            order=2,
            defaults={'failover_type': type_vector},
        )
        FailoverStrategyStep.objects.get_or_create(
            strategy=strat_standard,
            order=3,
            defaults={'failover_type': type_strict},
        )

        # Local First: Local -> Vector -> Fail
        FailoverStrategyStep.objects.get_or_create(
            strategy=strat_local_first,
            order=1,
            defaults={'failover_type': type_local},
        )
        FailoverStrategyStep.objects.get_or_create(
            strategy=strat_local_first,
            order=2,
            defaults={'failover_type': type_vector},
        )
        FailoverStrategyStep.objects.get_or_create(
            strategy=strat_local_first,
            order=3,
            defaults={'failover_type': type_strict},
        )

        # Strict: Family -> Fail
        FailoverStrategyStep.objects.get_or_create(
            strategy=strat_strict,
            order=1,
            defaults={'failover_type': type_family},
        )
        FailoverStrategyStep.objects.get_or_create(
            strategy=strat_strict,
            order=2,
            defaults={'failover_type': type_strict},
        )

    def _seed_financial_ecosystem(self):
        self.stdout.write('  -> Seeding Financial Governance (Budgets)...')

        # 1. Periods
        period_shift, _ = BudgetPeriod.objects.get_or_create(
            name='8-Hour Shift',
            defaults={
                'duration': timedelta(hours=8),
                'description': 'Standard working shift reset.',
            },
        )
        period_daily, _ = BudgetPeriod.objects.get_or_create(
            name='Daily',
            defaults={
                'duration': timedelta(days=1),
                'description': '24-hour rolling reset.',
            },
        )
        period_lifetime, _ = BudgetPeriod.objects.get_or_create(
            name='Lifetime',
            defaults={
                'duration': None,
                'description': 'Never resets. Hard ceiling.',
            },
        )

        # 2. Budgets
        IdentityBudget.objects.get_or_create(
            name='Intern / Free Tier',
            defaults={
                'period': period_daily,
                'max_input_cost_per_token': Decimal(
                    '0.0'
                ),  # Only free models allowed
                'max_output_cost_per_token': Decimal('0.0'),
                'max_spend_per_period': Decimal('0.0'),
            },
        )

        IdentityBudget.objects.get_or_create(
            name='Senior Engineer Shift',
            defaults={
                'period': period_shift,
                'max_input_cost_per_token': Decimal(
                    '0.00003'
                ),  # Allows premium models like Claude 3.5 Sonnet / GPT-4o
                'max_output_cost_per_token': Decimal('0.00015'),
                'max_spend_per_period': Decimal(
                    '5.00'
                ),  # $5 cap per 8-hour shift
                'warn_at_percent': 80,
            },
        )

        IdentityBudget.objects.get_or_create(
            name='Executive Synthesis',
            defaults={
                'period': period_daily,
                'max_input_cost_per_token': Decimal(
                    '0.00001'
                ),  # Prefers cheaper input for massive context reading
                'max_spend_per_period': Decimal('20.00'),
                'warn_at_percent': 90,
            },
        )

    def _seed_selection_filters(self):
        self.stdout.write(
            '  -> Seeding AI Model Selection Filters (Task Profiles)...'
        )

        # Grab strategies to link
        strat_standard = FailoverStrategy.objects.get(name='Standard Cloud')
        strat_local_first = FailoverStrategy.objects.get(name='Local First')

        # 1. The Coder Task Profile
        filter_engineer, _ = AIModelSelectionFilter.objects.get_or_create(
            name='Core Engineering Task',
            defaults={
                'failover_strategy': strat_standard,
            },
        )
        # Note: You would add `required_capabilities` (like function_calling) here using filter_engineer.required_capabilities.add(...) once those exist in your DB.

        # 2. The Creative/Artist Profile
        filter_artist, _ = AIModelSelectionFilter.objects.get_or_create(
            name='Creative Brainstorming',
            defaults={
                'failover_strategy': strat_local_first,
            },
        )
