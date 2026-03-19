from uuid import UUID

from django.db import models
from pgvector.django import VectorField

from common.models import (
    CreatedAndModifiedWithDelta,
    DescriptionMixin,
    NameMixin,
    UUIDIdMixin,
)
from frontal_lobe.models import ModelRegistry, ReasoningTurn
from hippocampus.models import TalosEngram
from hypothalamus.hypothalamus import Hypothalamus, ModelSelection
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
        'hypothalamus.AIModelCategory', on_delete=models.PROTECT
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

    THALAMUS = UUID('2e50d62a-e6ec-489e-84ce-0a1ea2101a73')

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

    @classmethod
    def get_or_create_thalamus(cls):
        return IdentityDisc.objects.get_or_create(id=cls.THALAMUS)

    def update_vector(self):
        """Generates a vector for this IdentityDisc."""
        from frontal_lobe.synapse import OllamaClient

        registry = ModelRegistry.objects.get(id=ModelRegistry.NOMIC_EMBED_TEXT)
        client = OllamaClient(registry.name)
        tag_names = ', '.join(self.tags.values_list('name', flat=True))
        rich_text = (
            f'Tags: {tag_names}.'
            f'Type: {self.identity_type.name}.'
            f'Prompt: {self.system_prompt_template}'
        )
        self.vector = client.embed(rich_text)
        self.save(update_fields=['vector'])

    def ai_model(self, payload_size: int) -> ModelSelection:
        """Returns the optimal AI model for this IdentityDisc."""
        return Hypothalamus.pick_optimal_model(self, payload_size)
