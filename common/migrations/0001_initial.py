"""Bootstrap migration that installs the pgvector extension.

`common` has no concrete models, only mixins — so this migration exists
solely to install Postgres extensions that downstream apps depend on.
Every app that declares a `VectorField` (hippocampus, hypothalamus,
identity) depends on this migration so the extension is guaranteed to
exist before the tables that use it are created.

Without this migration, a fresh test database fails to build with
`type "vector" does not exist` during `CREATE TABLE` for vector columns.
"""

from django.db import migrations

from pgvector.django import VectorExtension


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        VectorExtension(),
    ]
