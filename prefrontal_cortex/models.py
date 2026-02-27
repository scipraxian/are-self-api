from django.core.exceptions import ValidationError
from django.db import models

from common.models import (
    CreatedAndModifiedWithDelta,
    CreatedMixin,
    DescriptionMixin,
    ModifiedMixin,
    NameMixin,
    UUIDIdMixin,
    VectorMixin,
)
from environments.models import ProjectEnvironment


class PFCItemStatus(NameMixin):
    """Lookup table for Agile States."""

    BACKLOG = 1
    SELECTED_FOR_DEVELOPMENT = 2
    IN_PROGRESS = 3
    BLOCKED_BY_USER = 4
    DONE = 5


class PFCEpic(
    UUIDIdMixin,
    NameMixin,
    DescriptionMixin,
    CreatedAndModifiedWithDelta,
    VectorMixin,
):
    """The High-Level Directives (Written by Humans).
    If the environment is set, the epic is scoped to that environment.
    """

    RELATED_NAME = 'epics'

    status = models.ForeignKey(
        PFCItemStatus, on_delete=models.PROTECT, default=PFCItemStatus.BACKLOG
    )
    environment = models.ForeignKey(
        ProjectEnvironment,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name=RELATED_NAME,
    )


class PFCStory(
    UUIDIdMixin,
    NameMixin,
    DescriptionMixin,
    CreatedAndModifiedWithDelta,
    VectorMixin,
):
    """The Strategies (Written by Humans or Talos)."""

    epic = models.ForeignKey(
        PFCEpic, on_delete=models.CASCADE, related_name='stories'
    )
    status = models.ForeignKey(
        PFCItemStatus, on_delete=models.PROTECT, default=PFCItemStatus.BACKLOG
    )


class PFCTask(
    UUIDIdMixin,
    NameMixin,
    DescriptionMixin,
    CreatedAndModifiedWithDelta,
    VectorMixin,
):
    """The Tactics (Written strictly by Talos). Replaces ReasoningGoal."""

    story = models.ForeignKey(
        PFCStory, on_delete=models.CASCADE, related_name='tasks'
    )
    status = models.ForeignKey(
        PFCItemStatus, on_delete=models.PROTECT, default=PFCItemStatus.BACKLOG
    )


class PFCComment(UUIDIdMixin, CreatedMixin, ModifiedMixin):
    """A Comment on an Item. If user is None, the comment is made by Talos."""

    RELATED_NAME = 'comments'

    user = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='+',
        blank=True,
        null=True,
    )
    text = models.TextField()
    epic = models.ForeignKey(
        PFCEpic,
        on_delete=models.CASCADE,
        related_name=RELATED_NAME,
        blank=True,
        null=True,
    )
    story = models.ForeignKey(
        PFCStory,
        on_delete=models.CASCADE,
        related_name=RELATED_NAME,
        blank=True,
        null=True,
    )
    task = models.ForeignKey(
        PFCTask,
        on_delete=models.CASCADE,
        related_name=RELATED_NAME,
        blank=True,
        null=True,
    )

    def __str__(self):
        return (
            f'Comment by {self.user.username if self.user else "Talos"} '
            f'on {self.epic or self.story or self.task}'
        )

    def clean(self):
        targets = [self.epic, self.story, self.task]
        if sum(1 for t in targets if t) != 1:
            raise ValidationError(
                'Comment must be attached to exactly one of: '
                'epic, story, or task.'
            )
