"""./manage.py pack_modifier <slug> — zip a genome bundle into the catalog.

Dev-flow only: reads ``modifier_genome/<slug>/`` and writes
``neural_modifier_catalog/<slug>.zip``. The catalog dir is gitignored;
this command is what materializes a freshly-cloned source bundle into
something the Modifier Garden's Install button can act on.

This is the parallel of ``build_modifier`` (which installs from genome
into the runtime tree). ``pack_modifier`` packs from genome into the
catalog. Both are dev-only. The frontend never invokes either — it goes
through the catalog REST surface.
"""

import zipfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from neuroplasticity import loader


class Command(BaseCommand):
    help = (
        'Zip modifier_genome/<slug>/ into '
        'neural_modifier_catalog/<slug>.zip (dev-only).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'slug',
            help='Bundle slug — must match the modifier_genome/<slug>/ dir.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite an existing catalog zip with the same slug.',
        )

    def handle(self, *args, **options):
        slug = options['slug']
        force = options['force']

        source = loader.modifier_genome_root() / slug
        if not source.is_dir():
            raise CommandError(
                'No genome source at {0}.'.format(source)
            )

        catalog = loader.catalog_root()
        catalog.mkdir(parents=True, exist_ok=True)
        target = catalog / '{0}.zip'.format(slug)
        if target.exists() and not force:
            raise CommandError(
                'Catalog already contains {0}; pass --force to overwrite.'.format(
                    target.name
                )
            )
        if target.exists():
            target.unlink()

        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(source.rglob('*')):
                if path.is_dir():
                    continue
                # Skip __pycache__ and .pyc — derived state, never ship.
                if '__pycache__' in path.parts or path.suffix == '.pyc':
                    continue
                arcname = Path(slug) / path.relative_to(source)
                zf.write(path, arcname.as_posix())

        self.stdout.write(
            self.style.SUCCESS(
                'Packed {0} -> {1}.'.format(source, target)
            )
        )
