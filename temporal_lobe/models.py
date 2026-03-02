from django.db import models

from common.constants import STANDARD_CHARFIELD_LENGTH
from common.models import CreatedAndModifiedWithDelta, NameMixin
from identity.models import Identity


class Shift(NameMixin):
    """Execute N number of turns."""

    GROOMING = 1
    PRE_PLANNING = 2
    PLANNING = 3
    EXECUTING = 4
    POST_EXECUTION = 5
    turn_limit = models.IntegerField(default=1)


class ShiftParticipant(models.Model):
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE)
    participant = models.ForeignKey(Identity, on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.participant} - {self.shift}'


class IterationDefinition(NameMixin):
    pass


class IterationShift(models.Model):
    definition = models.ForeignKey(
        IterationDefinition, on_delete=models.CASCADE
    )
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']
        unique_together = ('definition', 'order')


class IterationStatus(NameMixin):
    WAITING = 1
    RUNNING = 2
    FINISHED = 3
    CANCELLED = 4
    BLOCKED_BY_USER = 5
    ERROR = 6


class Iteration(CreatedAndModifiedWithDelta):
    name = models.CharField(
        max_length=STANDARD_CHARFIELD_LENGTH, blank=True, null=True
    )
    environment = models.ForeignKey(
        'environments.ProjectEnvironment',
        on_delete=models.PROTECT,
        blank=True,
        null=True,
    )
    status = models.ForeignKey(IterationStatus, on_delete=models.CASCADE)
    definition = models.ForeignKey(
        IterationDefinition, on_delete=models.PROTECT
    )
    current_shift = models.ForeignKey(IterationShift, on_delete=models.PROTECT)
    turns_consumed_in_shift = models.IntegerField(default=0)
