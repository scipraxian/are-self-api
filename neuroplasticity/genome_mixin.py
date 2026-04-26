from django.db import models

from neuroplasticity.models import NeuralModifier


class GenomeOwnedMixin(models.Model):
    """
    Rows that belong to a NeuralModifier bundle ('genome'). NULL is
    rejected at the schema level; every owned row resolves to a real
    NeuralModifier.

    genome=CANONICAL  -> core row; fixture-shipped (genetic_immutables /
                         zygote / initial_phenotypes); git-managed; never
                         mutated at runtime.
    genome=INCUBATOR  -> default user workspace; runtime creates land here
                         unless the request specifies a different active
                         genome.
    genome=<bundle>   -> contributed by an installed bundle; serialized
                         into genomes/<slug>.zip on Save-to-Genome,
                         CASCADE-deleted on uninstall.
    """

    genome = models.ForeignKey(
        NeuralModifier,
        on_delete=models.CASCADE,
        null=False,
        related_name='+',
        db_index=True,
        default=NeuralModifier.INCUBATOR,
    )

    class Meta:
        abstract = True
