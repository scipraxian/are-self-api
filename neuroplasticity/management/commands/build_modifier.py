"""./manage.py build_modifier <slug> — install a NeuralModifier bundle.

Copies neuroplasticity/modifier_genome/<slug>/ to neural_modifiers/<slug>/,
verifies the manifest, imports the entry modules, deserializes
modifier_data.json with one NeuralModifierContribution row per object
created, and flips the bundle's status to INSTALLED.
"""

from django.core.management.base import BaseCommand, CommandError

from neuroplasticity import loader


class Command(BaseCommand):
    help = 'Install a NeuralModifier bundle from modifier_genome/<slug>/.'

    def add_arguments(self, parser):
        parser.add_argument(
            'slug',
            help='Bundle slug — must match the modifier_genome/<slug>/ dir.',
        )

    def handle(self, *args, **options):
        slug = options['slug']
        try:
            modifier = loader.install_bundle(slug)
        except FileNotFoundError as exc:
            raise CommandError(str(exc))
        except FileExistsError as exc:
            raise CommandError(
                '{0}\nHint: ./manage.py uninstall_modifier {1}'.format(
                    exc, slug
                )
            )
        except Exception as exc:
            raise CommandError(
                'Install failed for {0}: {1}'.format(slug, exc)
            )
        self.stdout.write(
            self.style.SUCCESS(
                'Installed {0} (status={1}, contributions={2}).'.format(
                    modifier.slug,
                    modifier.status.name,
                    modifier.contributions.count(),
                )
            )
        )
