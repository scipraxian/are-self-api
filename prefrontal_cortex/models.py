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

    NEEDS_REFINEMENT = 1  # PM/Worker refine and/or sift
    BACKLOG = 2  # Worker Bid, PM Prioritize
    SELECTED_FOR_DEVELOPMENT = 3  # Worker Commit, PM Do Nothing
    IN_PROGRESS = 4  # worker work, pm sift
    IN_REVIEW = 5  # worker review but no approval, PM Blocked by user Else Select for development w/ comment.
    BLOCKED_BY_USER = 6
    DONE = 7
    WILL_NOT_DO = 8

    class Meta:
        verbose_name = 'Status'
        verbose_name_plural = 'Statuses'
        ordering = ['id']


class PFCTag(NameMixin):
    """
    Native tagging system to avoid external dependency conflicts.
    """

    class Meta:
        verbose_name = 'Tag'
        verbose_name_plural = 'Tags'
        ordering = ['name']


class PFCTagsMixin(models.Model):
    tags = models.ManyToManyField(PFCTag, blank=True)

    class Meta:
        abstract = True


class PFCTicketMixin(models.Model):
    # Priority & Complexity (The Bid)
    priority = models.IntegerField(
        default=3, help_text='1=Critical, 2=High, 3=Normal, 4=Low'
    )
    # The EM Definition of Ready (DoR) Fields
    perspective = models.TextField(blank=True, default='')
    assertions = models.TextField(
        blank=True,
        default='',
        help_text="Testable steps starting with 'Assert'",
    )
    outside = models.TextField(
        blank=True, default='', help_text='What NOT to do'
    )
    dod_exceptions = models.TextField(blank=True, default='')
    dependencies = models.TextField(blank=True, default='')
    demo_specifics = models.TextField(blank=True, default='')

    source_engrams = models.ManyToManyField(
        'hippocampus.TalosEngram', blank=True
    )

    class Meta:
        abstract = True


class PFCAssignmentMixin(models.Model):
    owning_disc = models.ForeignKey(
        'identity.IdentityDisc',
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name='%(app_label)s_%(class)s_owned',
    )
    previous_owners = models.ManyToManyField(
        'identity.IdentityDisc',
        blank=True,
        related_name='%(app_label)s_%(class)s_previously_owned',
    )

    class Meta:
        abstract = True


class PFCEpic(
    UUIDIdMixin,
    NameMixin,
    DescriptionMixin,
    CreatedAndModifiedWithDelta,
    VectorMixin,
    PFCTagsMixin,
    PFCTicketMixin,
    PFCAssignmentMixin,
):
    """The High-Level Directives (Written by Humans, groomed by Are-Self).
    If the environment is set, the epic is scoped to that environment.
    """

    RELATED_NAME = 'epics'

    status = models.ForeignKey(
        PFCItemStatus,
        on_delete=models.PROTECT,
        default=PFCItemStatus.BLOCKED_BY_USER,
    )
    environment = models.ForeignKey(
        ProjectEnvironment,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name=RELATED_NAME,
    )
    complexity = models.IntegerField(
        default=0, help_text='Read Only - Calculated Value'
    )


class PFCStory(
    UUIDIdMixin,
    NameMixin,
    DescriptionMixin,
    CreatedAndModifiedWithDelta,
    VectorMixin,
    PFCTagsMixin,
    PFCTicketMixin,
    PFCAssignmentMixin,
):
    """The Strategies (Written by Humans or Are-Self)."""

    RELATED_NAME = 'stories'

    epic = models.ForeignKey(
        PFCEpic, on_delete=models.CASCADE, related_name=RELATED_NAME
    )
    status = models.ForeignKey(
        PFCItemStatus,
        on_delete=models.PROTECT,
        default=PFCItemStatus.NEEDS_REFINEMENT,
    )
    complexity = models.IntegerField(default=0, help_text='Worker Calculated.')


class PFCTask(
    UUIDIdMixin,
    NameMixin,
    DescriptionMixin,
    CreatedAndModifiedWithDelta,
    VectorMixin,
    PFCTagsMixin,
    PFCAssignmentMixin,
):
    """The Tactics (Written strictly by Are-Self). Replaces ReasoningGoal."""

    story = models.ForeignKey(
        PFCStory, on_delete=models.CASCADE, related_name='tasks'
    )
    status = models.ForeignKey(
        PFCItemStatus,
        on_delete=models.PROTECT,
        default=PFCItemStatus.SELECTED_FOR_DEVELOPMENT,
    )


class PFCCommentStatus(NameMixin):
    """Lookup table for Comment Statuses."""

    CREATED = 1
    APPROVED = 2
    REJECTED = 3
    ARCHIVED = 4


class PFCComment(UUIDIdMixin, CreatedMixin, ModifiedMixin, PFCTagsMixin):
    """A Comment on an Item. If user is None, the comment is made by Talos."""

    RELATED_NAME = 'comments'

    status = models.ForeignKey(
        PFCCommentStatus, blank=True, null=True, on_delete=models.PROTECT
    )

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
