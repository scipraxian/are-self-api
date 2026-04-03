from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('central_nervous_system', '0002_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='effector',
            old_name='talos_executable',
            new_name='executable',
        ),
    ]
