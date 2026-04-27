"""Flip ``NeuralModifier.id`` from ``BigAutoField`` to ``UUIDField``.

Postgres cannot ``::uuid``-cast a ``bigint`` column — Django's stock
``AlterField(UUIDField)`` path generates ``ALTER COLUMN id TYPE uuid
USING id::uuid``, which fails even on empty tables. This migration
does the same state transition but with an explicit ``USING
gen_random_uuid()`` clause, accompanied by the FK-column flips on
every ``GenomeOwnedMixin``-bearing table.

The project is pre-production: no prod data relies on this PK shape
yet, and Michael nukes the dev DB before applying migrations. On any
non-nuked DB the conversion fabricates fresh UUIDs for existing rows
(losing FK linkage between NeuralModifier rows and their owned
children); no realistic deployment hits that path.
"""

from __future__ import annotations

import uuid

from django.db import migrations, models


# Every ``(table, column)`` FK that points at ``neuroplasticity_neuralmodifier.id``.
# Covers both ``GenomeOwnedMixin.genome`` FKs (the 12-ish consumer list)
# AND the in-app installation-log back-pointer. Any future FK to
# NeuralModifier must be added here.
FK_TABLES_TO_NEURALMODIFIER = (
    # GenomeOwnedMixin consumers
    ('central_nervous_system_effector', 'genome_id'),
    ('central_nervous_system_neuralpathway', 'genome_id'),
    ('environments_executable', 'genome_id'),
    ('environments_executableargument', 'genome_id'),
    ('environments_executableswitch', 'genome_id'),
    ('environments_projectenvironment', 'genome_id'),
    ('identity_identity', 'genome_id'),
    ('identity_identityaddon', 'genome_id'),
    ('identity_identitydisc', 'genome_id'),
    ('parietal_lobe_tooldefinition', 'genome_id'),
    ('parietal_lobe_toolparameter', 'genome_id'),
    ('temporal_lobe_iterationdefinition', 'genome_id'),
    # Installation log back-pointer (not a genome FK, but also a
    # FK to NeuralModifier that needs the same type flip).
    ('neuroplasticity_neuralmodifierinstallationlog', 'neural_modifier_id'),
)


def _forward_sql() -> list[str]:
    """Drop FKs → retype PK and FK columns → recreate FKs."""
    statements: list[str] = []

    # 1. Drop every FK pointing at ``neuroplasticity_neuralmodifier``.
    #    pg_constraint lets us do this generically — no need to guess
    #    Django's hashed constraint names.
    statements.append(
        "DO $$ DECLARE r record; BEGIN "
        "FOR r IN SELECT conname, conrelid::regclass AS tbl FROM pg_constraint "
        "WHERE confrelid = 'neuroplasticity_neuralmodifier'::regclass "
        "AND contype = 'f' "
        "LOOP EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.tbl, r.conname); "
        "END LOOP; END $$;"
    )

    # 2. Strip the BigAutoField default + sequence on
    #    ``neuralmodifier.id`` and retype to UUID. ``gen_random_uuid``
    #    requires Postgres 13+ OR the ``pgcrypto`` extension — both
    #    are present (pgcrypto is installed by every vector-using app
    #    in its own ``0001_initial``).
    # BigAutoField on Postgres 10+ is an IDENTITY column, not a
    # DEFAULT-backed sequence. DROP IDENTITY IF EXISTS handles both
    # old (sequence) and new (identity) layouts.
    statements.append(
        'ALTER TABLE "neuroplasticity_neuralmodifier" '
        'ALTER COLUMN "id" DROP IDENTITY IF EXISTS;'
    )
    statements.append(
        'ALTER TABLE "neuroplasticity_neuralmodifier" '
        'ALTER COLUMN "id" DROP DEFAULT;'
    )
    statements.append(
        'ALTER TABLE "neuroplasticity_neuralmodifier" '
        'ALTER COLUMN "id" TYPE uuid USING gen_random_uuid();'
    )

    # 3. Retype every genome_id FK column. Values are NULL on any
    #    fresh/nuked DB, so ``NULL::uuid`` is a no-op. On a populated
    #    DB linkage is wiped — same trade as the PK flip above.
    for table, column in FK_TABLES_TO_NEURALMODIFIER:
        statements.append(
            'ALTER TABLE "{0}" ALTER COLUMN "{1}" TYPE uuid '
            'USING NULL::uuid;'.format(table, column)
        )

    # 4. Recreate the FK constraints. Postgres assigns new
    #    constraint names; Django's ORM only cares that the
    #    relationship exists.
    for table, column in FK_TABLES_TO_NEURALMODIFIER:
        statements.append(
            'ALTER TABLE "{0}" ADD FOREIGN KEY ("{1}") '
            'REFERENCES "neuroplasticity_neuralmodifier" ("id") '
            'DEFERRABLE INITIALLY DEFERRED;'.format(table, column)
        )

    return statements


def _reverse_sql() -> list[str]:
    """Reverse path — back to bigint. Lossy in the same way."""
    statements: list[str] = []

    statements.append(
        "DO $$ DECLARE r record; BEGIN "
        "FOR r IN SELECT conname, conrelid::regclass AS tbl FROM pg_constraint "
        "WHERE confrelid = 'neuroplasticity_neuralmodifier'::regclass "
        "AND contype = 'f' "
        "LOOP EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.tbl, r.conname); "
        "END LOOP; END $$;"
    )
    statements.append(
        'ALTER TABLE "neuroplasticity_neuralmodifier" '
        'ALTER COLUMN "id" TYPE bigint USING 0;'
    )
    for table, column in FK_TABLES_TO_NEURALMODIFIER:
        statements.append(
            'ALTER TABLE "{0}" ALTER COLUMN "{1}" TYPE bigint '
            'USING NULL::bigint;'.format(table, column)
        )
    for table, column in FK_TABLES_TO_NEURALMODIFIER:
        statements.append(
            'ALTER TABLE "{0}" ADD FOREIGN KEY ("{1}") '
            'REFERENCES "neuroplasticity_neuralmodifier" ("id") '
            'DEFERRABLE INITIALLY DEFERRED;'.format(table, column)
        )
    return statements


class Migration(migrations.Migration):

    dependencies = [
        ('neuroplasticity', '0002_remove_neuralmodifiercontribution_neuroplasti_content_666299_idx_and_more'),
        ('central_nervous_system', '0003_effector_genome_neuralpathway_genome'),
        ('environments', '0003_executable_genome_executableargument_genome_and_more'),
        ('identity', '0002_identity_genome_identityaddon_genome_and_more'),
        ('parietal_lobe', '0002_tooldefinition_genome_toolparameter_genome'),
        ('temporal_lobe', '0002_iterationdefinition_genome'),
    ]

    operations = [
        migrations.RunSQL(
            sql=_forward_sql(),
            reverse_sql=_reverse_sql(),
            state_operations=[
                migrations.AlterField(
                    model_name='neuralmodifier',
                    name='id',
                    field=models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
            ],
        ),
    ]
