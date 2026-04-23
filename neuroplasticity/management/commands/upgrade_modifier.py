"""./manage.py upgrade_modifier <slug> — upgrade a NeuralModifier in place.

Compares the on-disk bundle version to the DB version. If newer, diffs
modifier_data.json PKs against the currently-owned rows (PKs with
``genome=<this modifier>`` across the twelve GenomeOwnedMixin models)
and applies create / update / delete selectively — unchanged owned
rows keep their PKs so external FKs into bundle-owned rows survive
across versions.
"""

from django.core.management.base import BaseCommand, CommandError

from neuroplasticity import loader


class Command(BaseCommand):
    help = 'Upgrade an installed NeuralModifier bundle in place.'

    def add_arguments(self, parser):
        parser.add_argument(
            'slug',
            help=(
                'Bundle slug — must match an already-installed '
                'NeuralModifier.'
            ),
        )
        parser.add_argument(
            '--allow-same-version',
            action='store_true',
            help='Run the diff even if versions match (for repairs).',
        )

    def handle(self, *args, **options):
        try:
            result = loader.upgrade_bundle(
                options['slug'],
                allow_same_version=options['allow_same_version'],
            )
        except Exception as exc:
            raise CommandError(
                'Upgrade failed for {0}: {1}'.format(options['slug'], exc)
            )
        self.stdout.write(
            self.style.SUCCESS(
                'Upgraded {slug}: {from_ver} -> {to_ver} '
                '(created={c}, updated={u}, deleted={d}).'.format(
                    slug=options['slug'],
                    from_ver=result['previous_version'],
                    to_ver=result['new_version'],
                    c=result['created'],
                    u=result['updated'],
                    d=result['deleted'],
                )
            )
        )
