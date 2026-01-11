from django.db import migrations


def create_initial_statuses(apps, schema_editor):
    ConsciousStatus = apps.get_model('talos_frontal', 'ConsciousStatus')
    ConsciousStatus.objects.create(id=1, name='Thinking')
    ConsciousStatus.objects.create(id=2, name='Waiting')
    ConsciousStatus.objects.create(id=3, name='Done')


def remove_initial_statuses(apps, schema_editor):
    ConsciousStatus = apps.get_model('talos_frontal', 'ConsciousStatus')
    ConsciousStatus.objects.filter(id__in=[1, 2, 3]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('talos_frontal', '0002_consciousstatus_alter_consciousstream_status'),
    ]

    operations = [
        migrations.RunPython(create_initial_statuses, remove_initial_statuses),
    ]
