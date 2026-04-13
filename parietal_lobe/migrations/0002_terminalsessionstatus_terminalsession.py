import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('frontal_lobe', '0001_initial'),
        ('parietal_lobe', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='TerminalSessionStatus',
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
                'verbose_name_plural': 'Terminal Session Statuses',
            },
        ),
        migrations.CreateModel(
            name='TerminalSession',
            fields=[
                (
                    'id',
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ('created', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('modified', models.DateTimeField(auto_now=True, db_index=True)),
                ('pid', models.IntegerField()),
                ('command', models.TextField()),
                ('workdir', models.CharField(blank=True, default='', max_length=1024)),
                ('stdout_buffer', models.TextField(blank=True, default='')),
                ('stderr_buffer', models.TextField(blank=True, default='')),
                (
                    'reasoning_session',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='terminal_sessions',
                        to='frontal_lobe.reasoningsession',
                    ),
                ),
                (
                    'status',
                    models.ForeignKey(
                        default=1,
                        on_delete=django.db.models.deletion.PROTECT,
                        to='parietal_lobe.terminalsessionstatus',
                    ),
                ),
            ],
        ),
    ]
