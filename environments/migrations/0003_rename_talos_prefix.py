from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('environments', '0002_initial'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='TalosExecutableSwitch',
            new_name='ExecutableSwitch',
        ),
        migrations.RenameModel(
            old_name='TalosExecutableArgument',
            new_name='ExecutableArgument',
        ),
        migrations.RenameModel(
            old_name='TalosExecutable',
            new_name='Executable',
        ),
        migrations.RenameModel(
            old_name='TalosExecutableArgumentAssignment',
            new_name='ExecutableArgumentAssignment',
        ),
        migrations.RenameModel(
            old_name='TalosExecutableSupplementaryFileOrPath',
            new_name='ExecutableSupplementaryFileOrPath',
        ),
    ]
