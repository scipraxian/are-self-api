# Supersedes legacy 0004 from the pre-merge line that deleted ModelProvider /
# ModelRegistry after 0003_reasoningsession_swarm_message_queue.  Main merged
# 0003 as reasoningturndigest; swarm and those deprecated models are already
# absent from 0001_initial, so the migration graph must still provide 0004 → 0005
# for 0006.  Databases that never had the tables: DROP IF EXISTS is a no-op.

from django.db import migrations


def _drop_if_exists(apps, schema_editor):
    """Remove deprecated tables if present (legacy installs only)."""
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        for table in ('frontal_lobe_modelprovider', 'frontal_lobe_modelregistry'):
            cursor.execute(
                'DROP TABLE IF EXISTS ' + connection.ops.quote_name(table)
            )


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('frontal_lobe', '0003_reasoningturndigest'),
    ]

    operations = [
        migrations.RunPython(_drop_if_exists, _noop),
    ]
