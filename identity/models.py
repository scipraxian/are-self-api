import shutil
from decimal import Decimal
from uuid import UUID

from django.db import models
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from pgvector.django import VectorField

from common.constants import STANDARD_CHARFIELD_LENGTH
from common.models import (
    CreatedAndModifiedWithDelta,
    DescriptionMixin,
    NameMixin,
    UUIDIdMixin,
)
from frontal_lobe.models import ReasoningTurn
from hippocampus.models import Engram
from identity.avatar_storage import avatar_media_dir
from neuroplasticity.genome_mixin import GenomeOwnedMixin
from neuroplasticity.models import NeuralModifier
from parietal_lobe.models import ToolDefinition


class IdentityAddonPhase(NameMixin):
    """When to Apply Addon."""

    IDENTIFY = 1  # System and Identity
    CONTEXT = 2  #  telemetry and focus...
    HISTORY = 3  # All previous messages to be included.
    TERMINAL = 4  # YOUR MOVE


class IdentityAddon(UUIDIdMixin, NameMixin, DescriptionMixin, GenomeOwnedMixin):
    """These are the different addons that can be applied to a persona."""

    phase = models.ForeignKey(
        IdentityAddonPhase, on_delete=models.SET_NULL, blank=True, null=True
    )
    function_slug = models.CharField(max_length=255, blank=True, null=True)
    addon_class_name = models.CharField(
        max_length=STANDARD_CHARFIELD_LENGTH, blank=True, null=True
    )


class IdentityTag(NameMixin):
    """These are the different tags that can be applied to a persona."""

    pass


class IdentityType(NameMixin):
    """These are the different types/categories of personas."""

    PM = 1
    WORKER = 2


class BudgetPeriod(NameMixin, DescriptionMixin):
    """
    The cadence at which spend resets.
    e.g. 'Daily', 'Monthly', 'Lifetime'
    duration=None signals a lifetime/never-reset budget.
    zero duration signals a one-time budget.
    """

    duration = models.DurationField(
        null=True,
        blank=True,
        help_text='Reset interval. Null = lifetime, never resets.',
    )


class IdentityBudget(NameMixin):
    """
    Limits for a persona, mapped strictly to per-token reality.
    Per-token fields gate MODEL SELECTION — only models priced within
    these bounds are eligible candidates.
    Total spend fields gate REQUEST EXECUTION — once hit, requests halt.
    """

    period = models.ForeignKey(
        BudgetPeriod,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text='How often spend counters reset. Null = lifetime.',
    )

    # --- Model Selection Gates ---
    # These feed directly into the Hypothalamus pre-filter.
    # 0.0 = free-tier only.
    max_input_cost_per_token = models.DecimalField(
        max_digits=25,
        decimal_places=15,
        default=Decimal('0'),
        help_text='Candidate models with higher input cost are excluded entirely.',
    )
    max_output_cost_per_token = models.DecimalField(
        max_digits=25,
        decimal_places=15,
        default=Decimal('0'),
        help_text='Candidate models with higher output cost are excluded entirely.',
    )

    # --- Execution Gates ---
    max_spend_per_period = models.DecimalField(
        max_digits=25,
        decimal_places=15,
        null=True,
        blank=True,
        help_text='Hard ceiling on total spend within the budget period. Null = unlimited.',
    )
    max_spend_per_request = models.DecimalField(
        max_digits=25,
        decimal_places=15,
        null=True,
        blank=True,
        help_text='Single-request cost ceiling. Null = unlimited.',
    )
    warn_at_percent = models.PositiveSmallIntegerField(
        default=80,
        help_text='Emit a warning signal when spend reaches this % of max_spend_per_period.',
    )


class AvatarSelectedDisplayType(NameMixin):
    """The type of avatar to use."""

    GENERATED = 1  # Default, zero size.
    FILE = 2  # NeuralModifier media file.
    URL = 3
    EMOJI = 4  # multiple characters.


class Avatar(UUIDIdMixin, NameMixin, DescriptionMixin, GenomeOwnedMixin):
    """A visual representation of an identity, used for display and branding.

    Genome-owned: every Avatar row carries a ``genome`` FK via
    ``GenomeOwnedMixin``. ``display=FILE`` rows store their bytes in
    the owning genome's graft tree at::

        neuroplasticity/grafts/<genome.slug>/media/<stored_filename>

    and are served via the single core resolver at::

        /api/v2/genomes/<genome.slug>/media/<stored_filename>

    (one route in ``neuroplasticity/urls.py``, not per-genome).

    Canonical genome has no graft tree (no manifest, no install
    path), so canonical Avatar rows must use ``display`` ∈ {GENERATED,
    URL, EMOJI} only — never FILE. ``GenomeWritableMixin`` already
    refuses every API write that targets canonical, so canonical
    Avatar rows are fixture-only by construction; their display-kind
    constraint is a coding-time invariant on whoever ships the
    fixture.

    Curated default art ships as its own genome (Nano pack,
    HSH-aliens pack), not in canonical.
    """

    display = models.ForeignKey(
        AvatarSelectedDisplayType, default=1, on_delete=models.PROTECT
    )

    original_filename = models.CharField(
        max_length=STANDARD_CHARFIELD_LENGTH, blank=True, null=True
    )
    stored_filename = models.CharField(
        max_length=STANDARD_CHARFIELD_LENGTH, blank=True, null=True
    )

    url = models.URLField(blank=True, null=True)
    emoji = models.CharField(
        max_length=STANDARD_CHARFIELD_LENGTH, blank=True, null=True
    )
    tint_color = models.CharField(
        max_length=STANDARD_CHARFIELD_LENGTH, blank=True, null=True
    )

    def save(self, *args, **kwargs):
        # When ``genome`` changes on a ``display=FILE`` row, the bytes
        # under ``<grafts>/<old_slug>/media/`` need to travel to
        # ``<grafts>/<new_slug>/media/`` so the next
        # ``save_graft_to_genome`` bakes them into the correct zip.
        # Snapshot via ``values_list`` (not ``refresh_from_db``) to
        # avoid deferred-fields recursion through this same override.
        old_genome_id = None
        old_stored_filename = None
        if self.pk and not self._state.adding:
            old = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list('genome_id', 'stored_filename')
                .first()
            )
            if old is not None:
                old_genome_id, old_stored_filename = old

        super().save(*args, **kwargs)

        if (
            old_genome_id is None
            or old_genome_id == self.genome_id
            or self.display_id != AvatarSelectedDisplayType.FILE
            or not old_stored_filename
        ):
            return

        old_genome = NeuralModifier.objects.filter(pk=old_genome_id).first()
        if old_genome is None:
            return
        source = avatar_media_dir(old_genome) / old_stored_filename
        if not source.exists():
            return
        target_dir = avatar_media_dir(self.genome)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / (self.stored_filename or old_stored_filename)
        shutil.move(str(source), str(target))


class IdentityFields(GenomeOwnedMixin):
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
    category = models.ForeignKey(
        'hypothalamus.AIModelCategory',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    selection_filter = models.ForeignKey(
        'hypothalamus.AIModelSelectionFilter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text='Scope this budget to a specific filter. Null = applies globally.',
    )
    avatar = models.ForeignKey(
        Avatar, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        abstract = True


class Identity(
    UUIDIdMixin, NameMixin, CreatedAndModifiedWithDelta, IdentityFields
):
    """These are the details used to represent a persona."""

    THALAMUS = UUID('14148e25-283d-4547-a17d-e28d021eba07')


class IdentityDiscVector(models.Model):
    identity_disc = models.OneToOneField(
        'identity.IdentityDisc',
        on_delete=models.CASCADE,
        related_name='vector_node',
    )
    embeddings = VectorField(dimensions=768, null=True, blank=True)


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
    memories = models.ManyToManyField(Engram, blank=True)

    @property
    def vector(self):
        """Silently fetches the vector from the 1:1 table."""
        # hasattr check is necessary because the reverse 1:1 raises RelatedObjectDoesNotExist if missing
        if hasattr(self, 'vector_node'):
            return self.vector_node.embeddings
        return None

    @vector.setter
    def vector(self, value):
        """Silently updates or creates the 1:1 record when you do `disc.vector = new_array`."""
        if not hasattr(self, 'vector_node'):
            IdentityDiscVector.objects.create(
                identity_disc=self, embeddings=value
            )
        else:
            self.vector_node.embeddings = value
            self.vector_node.save(update_fields=['embeddings'])

    def save(self, *args, **kwargs):
        # Compare against the persisted row to decide if vector regen is
        # needed. Reading from the DB (via ``values_list``, NOT
        # ``refresh_from_db``) avoids constructing a deferred-fields
        # instance — Django would route that back through
        # ``Model.__init__`` and recurse on any field this method later
        # touches. Mirrors the genome save() fan-out pattern on
        # NeuralPathway / Effector / Executable.
        needs_vector = False
        if self.pk and not self._state.adding:
            old = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list(
                    'system_prompt_template',
                    'identity_type_id',
                )
                .first()
            )
            if old is not None and (
                self.system_prompt_template != old[0]
                or self.identity_type_id != old[1]
            ):
                needs_vector = True

        super().save(*args, **kwargs)

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

        result = client.embed(rich_text)
        if result:
            self.vector = result


@receiver(m2m_changed, sender=IdentityDisc.addons.through)
@receiver(m2m_changed, sender=IdentityDisc.tags.through)
def identity_disc_m2m_changed(sender, instance, action, **kwargs):
    """
    Automatically recalculate the Disc's vector if Addons or Tags are added, removed, or cleared.
    """
    # If Django is loading fixtures (raw=True), do nothing.
    if kwargs.get('raw', False):
        return

    # Only fire after the database has actually finished adding/removing the relations
    if action in ['post_add', 'post_remove', 'post_clear']:
        instance.update_vector()


class IdentityBudgetAssignment(CreatedAndModifiedWithDelta):
    """
    Binds an Identity to a Budget, optionally scoped to a specific SelectionFilter.

    Scoping logic:
      - selection_filter=None  →  budget applies to ALL requests from this identity.
      - selection_filter=<obj> →  budget applies only when that filter is active
                                  (e.g., a specific Persona or Task type).

    This lets you give an identity a global budget AND per-persona sub-budgets
    without any ambiguity — just create two assignments.
    """

    identity_disc = models.OneToOneField(
        IdentityDisc,
        on_delete=models.CASCADE,
        related_name='budget_assignments',
    )
    budget = models.ForeignKey(
        IdentityBudget,
        on_delete=models.PROTECT,  # Never silently remove a financial constraint
        related_name='assignments',
    )
    selection_filter = models.ForeignKey(
        'hypothalamus.AIModelSelectionFilter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='budget_assignments',
        help_text='Scope this budget to a specific filter. Null = applies globally.',
    )
    is_active = models.BooleanField(default=True, db_index=True)
    period_spend_start = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the current period started. Used to compute rolling spend against AIModelProviderUsageRecord.',
    )

    class Meta:
        verbose_name = 'Identity Budget Assignment'
        verbose_name_plural = 'Identity Budget Assignments'
        # An identity can have one active budget per filter scope at a time
        unique_together = [('identity_disc', 'selection_filter', 'is_active')]
