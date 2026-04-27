"""Add ``selected_for_edit`` to ``NeuralModifier``.

Field-only migration. The fixture (``genetic_immutables.json``) carries
the bool value for the canonical/incubator rows; runtime user bundles
default to ``False`` and flip via PATCH against the V2 viewset.
"""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('neuroplasticity', '0004_stamp_canonical_genome'),
    ]

    operations = [
        migrations.AddField(
            model_name='neuralmodifier',
            name='selected_for_edit',
            field=models.BooleanField(default=False),
        ),
    ]
