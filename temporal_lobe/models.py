from django.db import models

from common.constants import STANDARD_CHARFIELD_LENGTH
from common.models import CreatedAndModifiedWithDelta, NameMixin, UUIDIdMixin
from identity.models import Identity, IdentityDisc


class Shift(NameMixin):
    """Execute N number of turns."""

    SIFTING = 1  # pm refine epics and stories, # Worker BID on backlog
    PRE_PLANNING = 2  # pm based on
    # allocated turns and bids
    # prioritize epics and stories
    # move from needs refinement to backlog
    # move from backlog to selected for development (if bid)
    # worker sift
    PLANNING = 3  # Worker sift, PM sift
    EXECUTING = 4  # worker execute story, PM sift
    POST_EXECUTION = (
        5  # PM In Review to Blocked By User (else S4D), Worker BID on backlog
    )
    SLEEPING = 6  # Identity. Each identity sleeps by reviewing their memories and work, and growing.
    default_turn_limit = models.IntegerField(default=1)


class ShiftDefaultParticipant(models.Model):
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE)
    participant = models.ForeignKey(Identity, on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.participant} - {self.shift}'


class IterationDefinition(NameMixin):
    pass


class IterationShiftDefinition(models.Model):
    definition = models.ForeignKey(
        IterationDefinition, on_delete=models.CASCADE
    )
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE)
    order = models.IntegerField(default=0)
    turn_limit = models.IntegerField(default=1)

    class Meta:
        ordering = ['order']
        unique_together = ('definition', 'order')

    def __str__(self):
        return f'{self.definition} - {self.shift} ({self.order})'


class IterationShiftDefinitionParticipant(models.Model):
    shift_definition = models.ForeignKey(
        IterationShiftDefinition, on_delete=models.CASCADE
    )
    identity_disc = models.ForeignKey(
        IdentityDisc, on_delete=models.CASCADE, blank=True, null=True
    )

    def __str__(self):
        return f'{self.shift_definition} - {self.identity_disc}'


class IterationStatus(NameMixin):
    WAITING = 1
    RUNNING = 2
    FINISHED = 3
    CANCELLED = 4
    BLOCKED_BY_USER = 5
    ERROR = 6


class Iteration(UUIDIdMixin, CreatedAndModifiedWithDelta):
    name = models.CharField(
        max_length=STANDARD_CHARFIELD_LENGTH, blank=True, null=True
    )
    environment = models.ForeignKey(
        'environments.ProjectEnvironment',
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    status = models.ForeignKey(IterationStatus, on_delete=models.CASCADE)
    definition = models.ForeignKey(
        IterationDefinition, on_delete=models.CASCADE
    )
    current_shift = models.ForeignKey(
        'IterationShift', on_delete=models.SET_NULL, blank=True, null=True
    )
    turns_consumed_in_shift = models.IntegerField(default=0)

    def __str__(self):
        return self.name if self.name else f'Iteration {self.id}'


class IterationShift(CreatedAndModifiedWithDelta):
    definition = models.ForeignKey(
        IterationShiftDefinition, on_delete=models.CASCADE
    )
    shift_iteration = models.ForeignKey(Iteration, on_delete=models.CASCADE)
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.shift_iteration} - {self.shift}'


class IterationShiftParticipantStatus(NameMixin):
    SELECTED = 1
    ACTIVATED = 2
    COMPLETED = 3
    PAUSED = 4
    ERROR = 5

    class Meta:
        verbose_name = 'Iteration Shift Participant Status'
        verbose_name_plural = 'Iteration Shift Participant Statuses'


class IterationShiftParticipant(models.Model):
    iteration_shift = models.ForeignKey(
        IterationShift, on_delete=models.CASCADE
    )
    iteration_participant = models.ForeignKey(
        IdentityDisc, on_delete=models.CASCADE
    )
    status = models.ForeignKey(
        IterationShiftParticipantStatus,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    def __str__(self):
        return f'{self.iteration_shift} - {self.iteration_participant}'
