"""./manage.py list_modifiers — read-only dump of every NeuralModifier row."""

from django.core.management.base import BaseCommand

from neuroplasticity.models import NeuralModifier


class Command(BaseCommand):
    help = 'List every NeuralModifier with status, version, contribution count.'

    def handle(self, *args, **options):
        modifiers = NeuralModifier.objects.select_related('status').order_by(
            'slug'
        )
        if not modifiers.exists():
            self.stdout.write('(no NeuralModifiers registered)')
            return
        for modifier in modifiers:
            log = modifier.current_installation()
            last_install = log.created.isoformat() if log else '-'
            self.stdout.write(
                '{slug:<20} {status:<12} v{version:<10} '
                'contributions={contribs:<5} last={last}'.format(
                    slug=modifier.slug,
                    status=modifier.status.name,
                    version=modifier.version,
                    contribs=modifier.contributions.count(),
                    last=last_install,
                )
            )
