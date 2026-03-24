from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from hypothalamus.models import AIModelProvider, LLMProvider


class Command(BaseCommand):
    help = 'X-Ray vision for the Hypothalamus routing engine. See exactly where models are being filtered out.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--payload-size',
            type=int,
            default=1000,
            help='Simulated token count of the prompt + tools.',
        )
        parser.add_argument(
            '--max-cost',
            type=float,
            default=1.0,  # $1 per token is effectively infinite for testing
            help='Maximum input cost per token to simulate budget constraints.',
        )
        parser.add_argument(
            '--tools',
            action='store_true',
            help='Simulate passing a tool_payload (requires function_calling capability).',
        )

    def handle(self, *args, **options):
        payload_size = options['payload_size']
        max_cost = options['max_cost']
        needs_tools = options['tools']

        self.stdout.write(
            self.style.NOTICE(
                f'--- Starting Router Diagnostic --- \n'
                f'Parameters: Payload={payload_size} tokens | Max Cost=${max_cost}/token | Tools={needs_tools}\n'
            )
        )

        # Start with all providers
        qs = AIModelProvider.objects.all()
        total_models = qs.count()
        self.stdout.write(
            f'1. Total AIModelProviders in database: {total_models}'
        )
        if total_models == 0:
            self.stdout.write(
                self.style.ERROR(
                    '   -> Stop here. You have no models mapped to providers.'
                )
            )
            return

        # 1. API Key Check
        valid_provider_ids = [
            p.id
            for p in LLMProvider.objects.all()
            if not p.requires_api_key or p.has_active_key
        ]
        qs = qs.filter(provider_id__in=valid_provider_ids)
        self.stdout.write(
            f'2. After filtering for valid API Keys: {qs.count()}'
        )

        # 2. Circuit Breaker Check
        breaker_filter = Q(rate_limit_reset_time__isnull=True) | Q(
            rate_limit_reset_time__lte=timezone.now()
        )
        qs = qs.filter(breaker_filter)
        self.stdout.write(
            f'3. After removing rate-limited models: {qs.count()}'
        )

        # 3. Mode Check (Chat)
        qs = qs.filter(mode__name='chat')
        self.stdout.write(f"4. After filtering for 'chat' mode: {qs.count()}")

        # 4. Enabled Check (BOTH AIModel and AIModelProvider)
        qs = qs.filter(ai_model__enabled=True, is_enabled=True)
        self.stdout.write(
            f'5. After checking AIModel AND Provider are enabled: {qs.count()}'
        )

        # 5. Pricing Exists and is Active
        qs = qs.filter(
            aimodelpricing__is_current=True, aimodelpricing__is_active=True
        )
        self.stdout.write(
            f'6. After requiring active/current pricing: {qs.count()}'
        )

        # 6. Budget Constraints
        qs = qs.filter(aimodelpricing__input_cost_per_token__lte=max_cost)
        self.stdout.write(
            f'7. After enforcing budget (${max_cost}/token max): {qs.count()}'
        )

        # 7. Context Window
        qs = qs.filter(ai_model__context_length__gte=payload_size)
        self.stdout.write(
            f'8. After enforcing context window (>={payload_size} tokens): {qs.count()}'
        )

        # 8. Capabilities (Tools) & Scar Tissue
        if needs_tools:
            # Require the capability on the base model
            qs = qs.filter(ai_model__capabilities__name='function_calling')
            # EXCLUDE if the provider tripped on this capability and benched it
            qs = qs.exclude(disabled_capabilities__name='function_calling')
            self.stdout.write(
                f"9. After requiring 'function_calling' and excluding benched scar tissue: {qs.count()}"
            )

        # Results
        final_count = qs.count()
        if final_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✅ SUCCESS! {final_count} models survived the gauntlet.'
                )
            )
            self.stdout.write(
                'Here are the top 5 candidates that would be sent to the Vector router:'
            )

            # Use distinct to avoid duplicate rows from M2M joins before slicing
            for p in qs.distinct()[:5]:
                price = p.aimodelpricing_set.filter(is_current=True).first()
                cost_str = (
                    f'${price.input_cost_per_token}' if price else 'Unknown'
                )
                self.stdout.write(
                    f'   - {p.provider_unique_model_id} (Cost: {cost_str})'
                )
        else:
            self.stdout.write(
                self.style.ERROR(
                    '\n❌ FAILED! The routing pool is completely empty.'
                )
            )
