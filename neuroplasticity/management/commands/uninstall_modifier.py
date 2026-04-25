"""./manage.py uninstall_modifier <slug> — roll back a NeuralModifier bundle.

Walks the bundle's contributions in reverse-install order, deletes each
target, removes the runtime tree at ``grafts/<slug>/``, and DELETES the
``NeuralModifier`` row (contributions, logs, events cascade away). The
committed ``genomes/<slug>.zip`` stays put — the bundle returns to the
AVAILABLE state.
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
            deleted_slug = loader.uninstall_bundle(slug)
        except NeuralModifier.DoesNotExist:
            raise CommandError(
                'No NeuralModifier with slug {0!r}.'.format(slug)
            )
        self.stdout.write(
            self.style.SUCCESS(
                'Uninstalled {0}. Bundle is now AVAILABLE.'.format(
                    deleted_slug
                )
            )
        )
