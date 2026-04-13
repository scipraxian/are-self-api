from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('central_nervous_system', '0003_rename_talos_executable_to_executable'),
    ]

    operations = [
        migrations.RenameField(
            model_name='spike',
            old_name='blackboard',
            new_name='axoplasm',
        ),
        migrations.AddField(
            model_name='spiketrain',
            name='cerebrospinal_fluid',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
