"""Initial talos_gateway schema."""

import django.db.models.deletion
from django.db import migrations, models

import common.constants


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('frontal_lobe', '0003_reasoningsession_swarm_message_queue'),
    ]

    operations = [
        migrations.CreateModel(
            name='GatewaySessionStatus',
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
                    models.CharField(
                        max_length=common.constants.STANDARD_CHARFIELD_LENGTH
                    ),
                ),
            ],
            options={
                'verbose_name_plural': 'Gateway session statuses',
            },
        ),
        migrations.CreateModel(
            name='GatewaySession',
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
                    'created',
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                (
                    'modified',
                    models.DateTimeField(auto_now=True, db_index=True),
                ),
                ('platform', models.CharField(db_index=True, max_length=64)),
                (
                    'channel_id',
                    models.CharField(
                        db_index=True,
                        max_length=common.constants.STANDARD_CHARFIELD_LENGTH,
                    ),
                ),
                ('last_activity', models.DateTimeField(db_index=True)),
                (
                    'reasoning_session',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='gateway_sessions',
                        to='frontal_lobe.reasoningsession',
                    ),
                ),
                (
                    'status',
                    models.ForeignKey(
                        default=1,
                        on_delete=django.db.models.deletion.PROTECT,
                        to='talos_gateway.gatewaysessionstatus',
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name='gatewaysession',
            constraint=models.UniqueConstraint(
                fields=('platform', 'channel_id'),
                name='talos_gateway_gatewaysession_platform_channel_uniq',
            ),
        ),
    ]
