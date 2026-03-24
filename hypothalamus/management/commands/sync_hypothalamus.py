import logging

from django.core.management.base import BaseCommand

from hypothalamus.hypothalamus import Hypothalamus

logging.basicConfig(level=logging.INFO)


class Command(BaseCommand):
    help = 'Pulls the latest AI models and enriches them.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--use-cache',
            action='store_true',
            help='Skip OpenRouter network request and use local cache.',
        )
        parser.add_argument(
            '--force-rebuild',
            action='store_true',
            help='Force description remap and re-vectorize ALL models.',
        )
        parser.add_argument(
            '--semantics-only',
            action='store_true',
            help='Skip LiteLLM sync and only run the OpenRouter semantic enrichment.',
        )

    def handle(self, *args, **options):
        use_cache = options['use_cache']
        force_rebuild = options['force_rebuild']
        semantics_only = options['semantics_only']

        self.stdout.write(self.style.NOTICE('Waking up the Hypothalamus...'))

        try:
            if semantics_only:
                self.stdout.write(
                    self.style.WARNING('Running Semantics Only...')
                )
                modified_ids = (
                    Hypothalamus.enrich_model_semantics_from_openrouter(
                        use_local_cache=use_cache, force_rebuild=force_rebuild
                    )
                )
                if modified_ids:
                    Hypothalamus._trigger_vector_generation(modified_ids)
                self.stdout.write(
                    self.style.SUCCESS(f'Updated {len(modified_ids)} models.')
                )
            else:
                sync_log = Hypothalamus.sync_catalog(
                    use_local_cache=use_cache, force_rebuild=force_rebuild
                )
                if sync_log:
                    self.stdout.write(self.style.SUCCESS('Sync Complete!'))
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            'Sync aborted. Is it already running?'
                        )
                    )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Catastrophic failure: {e}'))
