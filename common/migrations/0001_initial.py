"""Legacy bootstrap migration for the pgvector extension.

Kept for historical compatibility with databases that already have this
migration recorded as applied. Each app that uses `VectorField` now
installs the extension as the first operation of its own `0001_initial`
migration, so this one is effectively a no-op — `VectorExtension()`
compiles to `CREATE EXTENSION IF NOT EXISTS vector`, which is idempotent.
"""

from django.db import migrations

from pgvector.django import VectorExtension


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        VectorExtension(),
    ]
