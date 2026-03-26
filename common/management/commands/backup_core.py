import logging
import os

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Safely backs up ONLY the structural/canonical models to initial_data.json fixtures using dynamic introspection.'

    # 100% Correct Approach: We only define the EXCLUSIONS (The Transactional "Buildings").
    # Everything else in the app is safely assumed to be a structural "Blueprint" and dumped.
    TRANSACTIONAL_MODELS = {
        'central_nervous_system': ['spike', 'spiketrain'],
        'django_celery_beat': [],
        'environments': [],
        'frontal_lobe': [
            'chatmessage',
            'reasoningengram',
            'reasoningsession',
            'reasoningspiketrainmap',
            'reasoningturn',
            'sessionconclusion',
        ],
        'hypothalamus': [
            'aimodeldescriptioncache',
            'aimodelpricing',
            'aimodelproviderusagerecord',
            'aimodelrating',
            'aimodelsynclog',
            'litellmcache',
        ],
        'identity': [],
        'parietal_lobe': ['toolcall'],
        'peripheral_nervous_system': ['nerveterminalregistry'],
        'prefrontal_cortex': ['pfccomment', 'pfcepic', 'pfcstory', 'pfctask'],
        'temporal_lobe': [
            'iteration',
            'iterationshift',
            'iterationshiftdefinitionparticipant',
            'iterationshiftparticipant',
        ],
    }

    def handle(self, *args, **options):
        base_dir = settings.BASE_DIR
        self.stdout.write(
            self.style.SUCCESS(
                'Starting strict core backup (Dynamic Introspection)...'
            )
        )

        for app_name, excluded_models in self.TRANSACTIONAL_MODELS.items():
            try:
                # Ask Django to load the actual app configuration
                app_config = apps.get_app_config(app_name)
            except LookupError:
                self.stdout.write(
                    self.style.ERROR(f"App '{app_name}' not found. Skipping.")
                )
                continue

            models_to_dump = []

            # Dynamically fetch every valid, registered database model for this app
            for model in app_config.get_models():
                model_name_lower = model.__name__.lower()

                # If it's not in the transactional blacklist, queue it for backup
                if model_name_lower not in excluded_models:
                    models_to_dump.append(f'{app_name}.{model_name_lower}')

            if not models_to_dump:
                self.stdout.write(
                    self.style.WARNING(
                        f"No structural models found for '{app_name}'. Skipping."
                    )
                )
                continue

            fixture_dir = os.path.join(base_dir, app_name, 'fixtures')
            os.makedirs(fixture_dir, exist_ok=True)
            output_file = os.path.join(fixture_dir, 'initial_data.json')

            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    # Pass the exact, Django-verified list of models to dumpdata
                    call_command(
                        'dumpdata', *models_to_dump, indent=2, stdout=f
                    )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully backed up {len(models_to_dump)} structural models for '{app_name}'"
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed to backup '{app_name}': {e}")
                )

        self.stdout.write(
            self.style.SUCCESS(
                'Core backup fully complete! Your fixtures are strictly transactional-free.'
            )
        )
