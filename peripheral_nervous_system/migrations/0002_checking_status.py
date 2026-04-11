"""Seed the CHECKING NerveTerminalStatus row (pk=4)."""

from django.db import migrations


CHECKING_PK = 4
CHECKING_NAME = 'Checking'


def add_checking_status(apps, schema_editor):
    NerveTerminalStatus = apps.get_model(
        'peripheral_nervous_system', 'NerveTerminalStatus'
    )
    NerveTerminalStatus.objects.update_or_create(
        pk=CHECKING_PK,
        defaults={'name': CHECKING_NAME},
    )


def remove_checking_status(apps, schema_editor):
    NerveTerminalStatus = apps.get_model(
        'peripheral_nervous_system', 'NerveTerminalStatus'
    )
    NerveTerminalStatus.objects.filter(pk=CHECKING_PK).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('peripheral_nervous_system', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(add_checking_status, remove_checking_status),
    ]
