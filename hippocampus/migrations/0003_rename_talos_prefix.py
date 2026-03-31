from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('hippocampus', '0002_initial'),
    ]

    operations = [
        migrations.RenameModel(old_name='TalosEngram', new_name='Engram'),
        migrations.RenameModel(
            old_name='TalosEngramTag', new_name='EngramTag'
        ),
    ]
