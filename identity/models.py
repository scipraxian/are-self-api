from django.db import models
from djangorestframework_mcp.types import MCPTool

from common.models import (
    CreatedAndModifiedWithDelta,
    DescriptionMixin,
    NameMixin,
    UUIDIdMixin,
)
from frontal_lobe.models import ReasoningTurn
from talos_hippocampus.models import TalosEngram
from talos_parietal.models import ToolDefinition


class IdentityAddon(NameMixin, DescriptionMixin):
    """These are the different addons that can be applied to a persona."""

    pass


class IdentityTag(NameMixin):
    """These are the different tags that can be applied to a persona."""

    pass


class IdentityType(NameMixin):
    """These are the different types/categories of personas."""

    pass


class Identity(UUIDIdMixin, NameMixin, CreatedAndModifiedWithDelta):
    """These are the details used to represent a persona."""

    identity_type = models.ForeignKey(
        IdentityType, on_delete=models.PROTECT, blank=True, null=True
    )
    tags = models.ManyToManyField(IdentityTag, blank=True)
    addons = models.ManyToManyField(IdentityAddon, blank=True)
    system_prompt_template = models.TextField(
        help_text='The core instructions given to the Frontal Lobe.'
    )
    enabled_tools = models.ManyToManyField(ToolDefinition, blank=True)


class IdentityDisc(UUIDIdMixin, NameMixin, CreatedAndModifiedWithDelta):
    """This is a persistent implementation of an identity."""

    identity = models.ForeignKey(Identity, on_delete=models.PROTECT)
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
