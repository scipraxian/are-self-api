"""./manage.py uninstall_modifier <slug> — roll back a NeuralModifier bundle.

Walks NeuralModifier.iter_contributed_objects() in install order, deletes
each target, removes contribution rows, deletes neural_modifiers/<slug>/
from disk, flips status to DISCOVERED. The NeuralModifier row itself is
preserved so the install history stays intact.
"""

from django.core.management.base import BaseCommand, CommandError

from neuroplasticity import loader
from neuroplasticity.models import NeuralModifier


class Command(BaseCommand):
    help = 'Uninstall a NeuralModifier bundle and roll back its contributions.'

    def add_arguments(self, parser):
        parser.add_argument('slug')

    def handle(self, *args, **options):
        slug = options['slug']
        try:
            modifier = loader.uninstall_bundle(slug)
        except NeuralModifier.DoesNotExist:
            raise CommandError(
                'No NeuralModifier with slug {0!r}.'.format(slug)
            )
        self.stdout.write(
            self.style.SUCCESS(
                'Uninstalled {0} (status={1}).'.format(
                    modifier.slug, modifier.status.name
                )
            )
        )
