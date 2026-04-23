from django.db import models

from neuroplasticity.models import NeuralModifier


class GenomeOwnedMixin(models.Model):
    """
    Rows that optionally belong to a NeuralModifier bundle ('genome').

    genome=null   -> core row (ships in genetic_immutables / zygote /
                     initial_phenotypes).
    genome=<uuid> -> contributed by a bundle; serialized back into
                     genomes/<slug>.zip on Save-to-Genome, CASCADE-deleted
                     on uninstall.
    """

    genome = models.ForeignKey(
        NeuralModifier,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='+',
        db_index=True,
    )

    class Meta:
        abstract = True
