"""
Management command: sample_pathway

Extract a single NeuralPathway as a portable fixture JSON,
automatically excluding anything already in the baseline genome
(genetic_immutables / zygote / initial_phenotypes).

Usage:
    python manage.py sample_pathway <pathway_uuid>
    python manage.py sample_pathway <pathway_uuid> --no-deps
    python manage.py sample_pathway <pathway_uuid> -o my_modifier.json
"""

import json

from django.core.management.base import BaseCommand

from central_nervous_system.sample_pathway import sample_pathway


class Command(BaseCommand):
    help = (
        'Export a single NeuralPathway (and its dependency closure) '
        'as a portable fixture JSON, minus baseline objects.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'pathway_id',
            type=str,
            help='UUID of the NeuralPathway to sample.',
        )
        parser.add_argument(
            '--no-deps',
            action='store_true',
            default=False,
            help=(
                'Only export the pathway subgraph (NeuralPathway, Neurons, '
                'NeuronContexts, Axons). Skip the Effector/Executable '
                'dependency chain.'
            ),
        )
        parser.add_argument(
            '-o',
            '--output',
            type=str,
            default=None,
            help='Write to file instead of stdout.',
        )

    def handle(self, *args, **options):
        pathway_id = options['pathway_id']
        include_deps = not options['no_deps']

        try:
            fixture = sample_pathway(
                pathway_id, include_dependencies=include_deps
            )
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Failed to sample: {e}'))
            return

        output = json.dumps(fixture, indent=2, ensure_ascii=False)

        if options['output']:
            with open(options['output'], 'w', encoding='utf-8') as f:
                f.write(output)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Sampled {len(fixture)} records → {options["output"]}'
                )
            )
        else:
            self.stdout.write(output)
