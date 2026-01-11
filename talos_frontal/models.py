from django.db import models
from hydra.models import HydraSpawn
from common.models import CreatedMixin, ModifiedMixin, BigIdMixin, NameMixin


class ConsciousStatusID:
    THINKING = 1
    WAITING = 2
    DONE = 3


class ConsciousStatus(BigIdMixin, NameMixin):
    """
    Lookup table for Consciousness States.
    """
    IDs = ConsciousStatusID

    class Meta:
        verbose_name_plural = "Conscious Statuses"


class ConsciousStream(CreatedMixin, ModifiedMixin):
    """
    The stream of thought for the Talos AGI.
    """
    spawn_link = models.ForeignKey(HydraSpawn,
                                   on_delete=models.CASCADE,
                                   related_name='thoughts')

    current_thought = models.TextField(
        help_text="The internal monologue or analysis result")

    status = models.ForeignKey(ConsciousStatus,
                               on_delete=models.PROTECT,
                               default=ConsciousStatusID.THINKING)

    def __str__(self):
        return f"Thought [{self.status.name}]: {self.current_thought[:50]}..."
