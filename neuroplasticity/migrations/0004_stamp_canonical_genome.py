"""Stamp every core-fixture row with ``genome=canonical``.

The Canonical Genome refactor replaces the overloaded two-state
(genome=NULL either "core fixture row" OR "user-created") with an
unambiguous three-state: ``canonical`` / ``<bundle>`` / NULL. This
migration is the bridge — it walks every app's committed
``genetic_immutables``, ``zygote``, and ``initial_phenotypes`` fixtures,
and for each row whose model is a ``GenomeOwnedMixin`` consumer it
points the ``genome`` FK at the single canonical ``NeuralModifier``
row.

Idempotent: ``update(genome_id=CANONICAL)`` is a no-op on a row
already stamped.

Reverse: sets genome_id back to NULL on rows currently pointing at
CANONICAL, so a rollback leaves the three-state collapsed back to
the old ambiguous two-state.

Note: On Michael's box the dev DB is nuked before applying migrations,
so this runs against a freshly-loaded fixture tree. For anyone else
rebuilding — the migration correctly re-derives the stamping set from
the committed fixture files on disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from django.apps import apps
from django.conf import settings
from django.db import migrations


CANONICAL_ID = UUID('8192d7fd-2d20-4109-9c7c-45121e89f1dd')
CANONICAL_SLUG = 'canonical'
FIXTURE_TIERS = ('genetic_immutables.json', 'zygote.json', 'initial_phenotypes.json')


def _genome_owned_model_keys(app_registry) -> set[str]:
    """Return ``{"app_label.modelname"}`` for every GenomeOwnedMixin model."""
    # Imported here so the migration remains usable under
    # ``ModelState``-only introspection in makemigrations dry-runs.
    from neuroplasticity.genome_mixin import GenomeOwnedMixin

    keys = set()
    for model in app_registry.get_models():
        if not issubclass(model, GenomeOwnedMixin):
            continue
        keys.add(
            '{0}.{1}'.format(
                model._meta.app_label, model._meta.model_name
            )
        )
    return keys


def _iter_fixture_rows(base_dir: Path, owned_keys: set[str]):
    """Yield (model_key, pk) for every GenomeOwnedMixin row in committed fixtures."""
    for app_path in sorted(base_dir.iterdir()):
        if not app_path.is_dir():
            continue
        fixtures_dir = app_path / 'fixtures'
        if not fixtures_dir.is_dir():
            continue
        for tier in FIXTURE_TIERS:
            fixture_path = fixtures_dir / tier
            if not fixture_path.exists():
                continue
            try:
                payload = json.loads(
                    fixture_path.read_text(encoding='utf-8')
                )
            except Exception:
                continue
            for row in payload:
                model_key = row.get('model')
                if model_key not in owned_keys:
                    continue
                pk = row.get('pk')
                if pk is None:
                    continue
                yield model_key, pk


def stamp_canonical(apps_registry, schema_editor):
    NeuralModifier = apps_registry.get_model(
        'neuroplasticity', 'NeuralModifier'
    )
    NeuralModifierStatus = apps_registry.get_model(
        'neuroplasticity', 'NeuralModifierStatus'
    )

    # Create the canonical row iff the status lookup table is populated.
    # On a fresh DB the fixtures ship the canonical row themselves
    # (``neuroplasticity/fixtures/genetic_immutables.json``) with
    # status_id=3, so skipping here is fine — ``loaddata`` will land it.
    # This branch exists for legacy DBs being upgraded in place.
    enabled = NeuralModifierStatus.objects.filter(name='Enabled').first()
    if enabled is not None:
        NeuralModifier.objects.update_or_create(
            pk=CANONICAL_ID,
            defaults={
                'slug': CANONICAL_SLUG,
                'name': 'Canonical',
                'version': '0.0.0',
                'author': 'scipraxian',
                'license': 'MIT',
                'manifest_hash': '',
                'manifest_json': {},
                'status': enabled,
            },
        )

    owned_keys = _genome_owned_model_keys(apps_registry)
    base_dir = Path(settings.BASE_DIR)

    by_model: dict[str, list] = {}
    for model_key, pk in _iter_fixture_rows(base_dir, owned_keys):
        by_model.setdefault(model_key, []).append(pk)

    for model_key, pks in by_model.items():
        app_label, model_name = model_key.split('.')
        Model = apps_registry.get_model(app_label, model_name)
        Model.objects.filter(pk__in=pks).update(genome_id=CANONICAL_ID)


def unstamp_canonical(apps_registry, schema_editor):
    """Reverse: blank the genome FK on rows currently pointing at canonical."""
    owned_keys = _genome_owned_model_keys(apps_registry)
    for model_key in owned_keys:
        app_label, model_name = model_key.split('.')
        Model = apps_registry.get_model(app_label, model_name)
        Model.objects.filter(genome_id=CANONICAL_ID).update(genome_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ('neuroplasticity', '0003_flip_neuralmodifier_to_uuid_pk'),
        # Every app that holds a ``genome`` FK must have the column
        # already added — depend on each of those schema migrations so
        # the update query has something to write to.
        ('central_nervous_system', '0003_effector_genome_neuralpathway_genome'),
        ('environments', '0003_executable_genome_executableargument_genome_and_more'),
        ('identity', '0002_identity_genome_identityaddon_genome_and_more'),
        ('parietal_lobe', '0002_tooldefinition_genome_toolparameter_genome'),
        ('temporal_lobe', '0002_iterationdefinition_genome'),
    ]

    operations = [
        migrations.RunPython(stamp_canonical, unstamp_canonical),
    ]
