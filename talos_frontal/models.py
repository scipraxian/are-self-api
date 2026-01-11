from django.db import models
from hydra.models import HydraSpawn
from common.models import CreatedMixin, ModifiedMixin


class ConsciousStream(CreatedMixin, ModifiedMixin):
    """
    The stream of thought for the Talos AGI.
    """

    class Status(models.TextChoices):
        THINKING = 'THINKING', 'Thinking'
        WAITING = 'WAITING', 'Waiting'
        DONE = 'DONE', 'Done'

    spawn_link = models.ForeignKey(HydraSpawn,
                                   on_delete=models.CASCADE,
                                   related_name='thoughts')
    current_thought = models.TextField(
        help_text="The internal monologue or analysis result")
    status = models.CharField(max_length=20,
                              choices=Status.choices,
                              default=Status.THINKING)

    def __str__(self):
        return f"Thought [{self.status}]: {self.current_thought[:50]}..."
