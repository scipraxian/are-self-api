from uuid import UUID

from django.db import models
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from pgvector.django import VectorField

from common.models import (
    CreatedAndModifiedWithDelta,
    DescriptionMixin,
    NameMixin,
    UUIDIdMixin,
)
from frontal_lobe.models import ReasoningTurn
from hippocampus.models import TalosEngram
from parietal_lobe.models import ToolDefinition


class IdentityAddonPhase(NameMixin):
    """When to Apply Addon."""

    IDENTIFY = 1  # System and Identity
    CONTEXT = 2  #  telemetry and focus...
    HISTORY = 3  # All previous messages to be included.
    TERMINAL = 4  # YOUR MOVE


class IdentityAddon(NameMixin, DescriptionMixin):
    """These are the different addons that can be applied to a persona."""

    phase = models.ForeignKey(
        IdentityAddonPhase, on_delete=models.SET_NULL, blank=True, null=True
    )
    function_slug = models.CharField(max_length=255, blank=True, null=True)


class IdentityTag(NameMixin):
    """These are the different tags that can be applied to a persona."""

    pass


class IdentityType(NameMixin):
    """These are the different types/categories of personas."""

    PM = 1
    WORKER = 2


class IdentityBudget(NameMixin):
    """
    Limits for a persona, mapped strictly to per-token reality.
    """

    max_input_cost_per_token = models.DecimalField(
        max_digits=25,  # Massive precision to handle things like 0.00000015
        decimal_places=15,
        default=0.000000000000000,
        help_text='Max Input Cost Per 1 Token. Set to 0.0 for strict Free only. (e.g., 0.00003 for GPT-4 level)',
    )


class IdentityFields(models.Model):
    """These are the details used to represent a persona."""

    identity_type = models.ForeignKey(
        IdentityType, on_delete=models.PROTECT, blank=True, null=True
    )
    tags = models.ManyToManyField(IdentityTag, blank=True)
    addons = models.ManyToManyField(IdentityAddon, blank=True)
    system_prompt_template = models.TextField(
        help_text='The core instructions given to the Frontal Lobe.',
        blank=True,
        null=True,
    )
    enabled_tools = models.ManyToManyField(ToolDefinition, blank=True)
    budget = models.ForeignKey(
        IdentityBudget, on_delete=models.SET_NULL, blank=True, null=True
    )
    category = models.ForeignKey(
        'hypothalamus.AIModelCategory',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )

    class Meta:
        abstract = True


class Identity(
    UUIDIdMixin, NameMixin, CreatedAndModifiedWithDelta, IdentityFields
):
    """These are the details used to represent a persona."""

    THALAMUS = UUID('14148e25-283d-4547-a17d-e28d021eba07')


class IdentityDisc(
    UUIDIdMixin, NameMixin, CreatedAndModifiedWithDelta, IdentityFields
):
    """This is a persistent implementation of an identity."""

    THALAMUS = UUID('15ca85b8-59a9-4cb6-9fd8-bfd2be47b838')

    available = models.BooleanField(default=True)
    last_message_to_self = models.TextField(blank=True, default='')
    level = models.IntegerField(default=1)
    xp = models.IntegerField(default=0)
    successes = models.IntegerField(default=0)
    failures = models.IntegerField(default=0)
    last_turn = models.ForeignKey(
        ReasoningTurn, on_delete=models.SET_NULL, null=True, blank=True
    )
    timeouts = models.IntegerField(default=0)
    memories = models.ManyToManyField(TalosEngram, blank=True)
    vector = VectorField(
        dimensions=768,
        null=True,
        blank=True,
    )

    def ai_model(self, payload_size: int):
        raise NotImplementedError(
            'AI model selection should be handled by Hypothalamus'
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Track the original state of the prompt so we know if it changes
        self._original_prompt = self.system_prompt_template
        self._original_type_id = self.identity_type_id

    def save(self, *args, **kwargs):
        # 1. Check if this is an existing record being updated
        needs_vector = False
        if self.pk:
            if (
                self.system_prompt_template != self._original_prompt
                or self.identity_type_id != self._original_type_id
            ):
                needs_vector = True

        # 2. Save the object normally first (so it gets a PK if it's new)
        super().save(*args, **kwargs)

        # 3. Update the tracking state
        self._original_prompt = self.system_prompt_template
        self._original_type_id = self.identity_type_id

        # 4. Fire the vector update if a base field changed
        if needs_vector:
            self.update_vector()

    def update_vector(self):
        """Generates a vector for this IdentityDisc, including Addon gravity."""
        from frontal_lobe.synapse import OllamaClient
        # TODO: repurpose the OllamaClient to be just Embedder.

        # Guard clause: Can't do M2M queries without a PK
        if not self.pk:
            return

        client = OllamaClient('nomic-embed-text')

        tag_names = ', '.join(self.tags.values_list('name', flat=True))

        # Grab all addon descriptions to create that "Semantic Gravity"
        addon_descriptions = ' '.join(
            filter(None, self.addons.values_list('description', flat=True))
        )

        type_name = self.identity_type.name if self.identity_type else 'Unknown'

        rich_text = (
            f'Tags: {tag_names}. '
            f'Type: {type_name}. '
            f'Addons: {addon_descriptions} '
            f'Prompt: {self.system_prompt_template or ""}'
        )

        self.vector = client.embed(rich_text)
        self.save(update_fields=['vector'])


@receiver(m2m_changed, sender=IdentityDisc.addons.through)
@receiver(m2m_changed, sender=IdentityDisc.tags.through)
def identity_disc_m2m_changed(sender, instance, action, **kwargs):
    """
    Automatically recalculate the Disc's vector if Addons or Tags are added, removed, or cleared.
    """
    # Only fire after the database has actually finished adding/removing the relations
    if action in ['post_add', 'post_remove', 'post_clear']:
        instance.update_vector()
