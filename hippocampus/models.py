from django.db import models
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from pgvector.django import VectorField

from central_nervous_system.models import Spike
from common.models import (
    CreatedMixin,
    DefaultFieldsMixin,
    DescriptionMixin,
    ModifiedMixin,
    NameMixin,
    UUIDIdMixin,
)
from frontal_lobe.models import ReasoningSession, ReasoningTurn
from prefrontal_cortex.models import PFCTask


class EngramTag(NameMixin):
    """A tag for categorizing engrams."""


class Engram(UUIDIdMixin, DefaultFieldsMixin, DescriptionMixin):
    """A single memory extracted during reasoning.

    args:
        name: A unique hash representing the memory content. You would use it to
        look up this memory in the future even if you didn't know you had it.
        description: The extracted fact or memory.

        session: The reasoning session this engram belongs to.
        source_turn: The reasoning turn this engram was extracted from.
        is_active: Indicates if the engram is currently active.
    """

    RELATED_NAME = 'engrams'

    sessions = models.ManyToManyField(
        ReasoningSession, related_name=RELATED_NAME, blank=True
    )
    source_turns = models.ManyToManyField(
        ReasoningTurn, related_name=RELATED_NAME, blank=True
    )
    spikes = models.ManyToManyField(
        Spike, related_name=RELATED_NAME, blank=True
    )
    tags = models.ManyToManyField(
        EngramTag, related_name=RELATED_NAME, blank=True
    )
    tasks = models.ManyToManyField(
        PFCTask, related_name=RELATED_NAME, blank=True
    )
    creator = models.ForeignKey(
        'identity.IdentityDisc',
        related_name='engrams_creator',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    identity_discs = models.ManyToManyField(
        'identity.IdentityDisc', related_name=RELATED_NAME, blank=True
    )

    is_active = models.BooleanField(default=True)
    relevance_score = models.FloatField(default=0.0)
    vector = VectorField(dimensions=768, null=True, blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_description = self.description

    def save(self, *args, **kwargs):
        needs_vector = (
            self.pk
            and self.description != self._original_description
        )
        super().save(*args, **kwargs)
        self._original_description = self.description
        if needs_vector:
            self.update_vector()

    def update_vector(self):
        """Generates a 768-dim embedding from name + description + tags."""
        from frontal_lobe.synapse import OllamaClient

        if not self.pk:
            return

        client = OllamaClient('nomic-embed-text')
        tag_names = ', '.join(self.tags.values_list('name', flat=True))
        text_payload = (
            f'Title: {self.name}\n'
            f'Tags: {tag_names}\n'
            f'Fact: {self.description}'
        )
        self.vector = client.embed(text_payload)
        super().save(update_fields=['vector'])


@receiver(m2m_changed, sender=Engram.tags.through)
def engram_tags_changed(sender, instance, action, **kwargs):
    """Recalculate the Engram vector when tags change."""
    if kwargs.get('raw', False):
        return
    if action in ['post_add', 'post_remove', 'post_clear']:
        instance.update_vector()


class SkillEngram(UUIDIdMixin, CreatedMixin, ModifiedMixin):
    """Procedural knowledge unit: SKILL.md content + metadata + linked files."""

    RELATED_NAME = 'skill_engrams'

    name = models.CharField(max_length=64, db_index=True, unique=True)
    description = models.CharField(max_length=200)
    category = models.CharField(
        max_length=64, db_index=True, blank=True, default=''
    )
    body = models.TextField()
    yaml_frontmatter = models.JSONField(default=dict, blank=True)
    vector = VectorField(dimensions=768, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    identity_disc = models.ForeignKey(
        'identity.IdentityDisc',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=RELATED_NAME,
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def __repr__(self):
        return f'SkillEngram(name={self.name!r})'


class SkillFileAttachment(UUIDIdMixin, CreatedMixin):
    """A file belonging to a SkillEngram (script, template, reference, asset)."""

    FILE_TYPE_CHOICES = [
        ('script', 'Script'),
        ('template', 'Template'),
        ('reference', 'Reference'),
        ('asset', 'Asset'),
    ]
    RELATED_NAME = 'attached_files'

    skill = models.ForeignKey(
        SkillEngram,
        on_delete=models.CASCADE,
        related_name=RELATED_NAME,
    )
    file_type = models.CharField(max_length=16, choices=FILE_TYPE_CHOICES)
    file_path = models.CharField(max_length=512)
    file_content = models.TextField(blank=True, default='')

    class Meta:
        unique_together = [['skill', 'file_path']]
        ordering = ['file_type', 'file_path']

    def __str__(self):
        return f'{self.file_type}: {self.file_path}'
