"""./manage.py enable_modifier <slug> — flip a NeuralModifier to ENABLED."""

from django.core.management.base import BaseCommand, CommandError

from neuroplasticity import loader
from neuroplasticity.models import NeuralModifier


class Command(BaseCommand):
    help = 'Enable a NeuralModifier (INSTALLED or DISABLED -> ENABLED).'

    def add_arguments(self, parser):
        parser.add_argument('slug')

    def handle(self, *args, **options):
        slug = options['slug']
        try:
            modifier = loader.enable_bundle(slug)
        except NeuralModifier.DoesNotExist:
            raise CommandError(
                'No NeuralModifier with slug {0!r}.'.format(slug)
            )
        self.stdout.write(
            self.style.SUCCESS(
                'Enabled {0} (status={1}).'.format(
                    modifier.slug, modifier.status.name
                )
            )
        )
