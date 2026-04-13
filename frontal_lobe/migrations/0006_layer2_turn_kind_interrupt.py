# ReasoningTurnKind, INTERRUPTED status, compression and interrupt fields

import django.db.models.deletion
import frontal_lobe.models
from django.db import migrations, models


def seed_reasoning_turn_kinds_and_status(apps, schema_editor):
    ReasoningTurnKind = apps.get_model('frontal_lobe', 'ReasoningTurnKind')
    ReasoningStatus = apps.get_model('frontal_lobe', 'ReasoningStatus')
    db_alias = schema_editor.connection.alias
    ReasoningTurnKind.objects.using(db_alias).get_or_create(
        id=1, defaults={'name': 'Normal'}
    )
    ReasoningTurnKind.objects.using(db_alias).get_or_create(
        id=2, defaults={'name': 'Summary'}
    )
    ReasoningStatus.objects.using(db_alias).get_or_create(
        id=9, defaults={'name': 'Interrupted'}
    )


def noop_reverse(apps, schema_editor):
    ReasoningStatus = apps.get_model('frontal_lobe', 'ReasoningStatus')
    db_alias = schema_editor.connection.alias
    ReasoningStatus.objects.using(db_alias).filter(id=9).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('frontal_lobe', '0005_alter_reasoningsession_current_focus'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReasoningTurnKind',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'name',
                    models.CharField(db_index=True, max_length=254, unique=True),
                ),
            ],
            options={
                'verbose_name_plural': 'Reasoning Turn Kinds',
            },
            bases=(models.Model, frontal_lobe.models.ReasoningTurnKindID),
        ),
        migrations.RunPython(
            seed_reasoning_turn_kinds_and_status, noop_reverse
        ),
        migrations.AddField(
            model_name='reasoningsession',
            name='interrupt_snapshot',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='reasoningturn',
            name='is_compressed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='reasoningturn',
            name='turn_kind',
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.PROTECT,
                to='frontal_lobe.reasoningturnkind',
            ),
            preserve_default=False,
        ),
    ]
