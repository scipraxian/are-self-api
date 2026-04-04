# Generated manually — drops deprecated ModelProvider and ModelRegistry tables.
# These are superseded by Hypothalamus AIModelProvider / AIModel.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('frontal_lobe', '0003_reasoningsession_swarm_message_queue'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ModelRegistry',
        ),
        migrations.DeleteModel(
            name='ModelProvider',
        ),
    ]
