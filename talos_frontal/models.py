import string

from django.db import models

from common.models import CreatedMixin, ModifiedMixin, BigIdMixin, NameMixin, DefaultFieldsMixin, UUIDIdMixin
from hydra.models import HydraSpawn


class SystemDirectiveIdentifierID(object):
    ANALYSIS_CORE = 1


class SystemDirectiveIdentifier(BigIdMixin, NameMixin):
    """
    Lookup table for Directive Types.
    """
    IDs = SystemDirectiveIdentifierID

    class Meta:
        verbose_name_plural = "System Directive Identifiers"


class ConsciousStatusID:
    THINKING = 1
    WAITING = 2
    DONE = 3


class ConsciousStatus(BigIdMixin, NameMixin):
    """
    Lookup table for Consciousness States.
    """
    IDs = ConsciousStatusID

    class Meta:
        verbose_name_plural = "Conscious Statuses"


class ConsciousStream(CreatedMixin, ModifiedMixin):
    """
    The stream of thought for the Talos AGI.
    """
    spawn_link = models.ForeignKey(HydraSpawn,
                                   on_delete=models.CASCADE,
                                   related_name='thoughts')

    head_link = models.ForeignKey('hydra.HydraHead',
                                  on_delete=models.SET_NULL,
                                  null=True,
                                  blank=True,
                                  related_name='thoughts')

    current_thought = models.TextField(
        help_text="The internal monologue or analysis result")

    status = models.ForeignKey(ConsciousStatus,
                               on_delete=models.PROTECT,
                               default=ConsciousStatusID.THINKING)

    def __str__(self):
        return f"Thought [{self.status.name}]: {self.current_thought[:50]}..."


class SystemDirective(DefaultFieldsMixin, UUIDIdMixin):
    """
    Defines the 'System Prompt'.
    """
    # THE FIX: ForeignKey, not CharField
    identifier = models.ForeignKey(
        SystemDirectiveIdentifier,
        on_delete=models.PROTECT,
        help_text="The functional type of this directive."
    )

    template = models.TextField()
    version = models.PositiveIntegerField(default=1, editable=False)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            # Auto-Increment Version based on identifier ID
            last = SystemDirective.objects.filter(
                identifier=self.identifier
            ).order_by('-version').first()
            if last:
                self.version = last.version + 1
        super().save(*args, **kwargs)

    @property
    def required_variables(self):
        """Extracts variables from the template string automatically."""
        formatter = string.Formatter()
        return [
            fname for _, fname, _, _ in formatter.parse(self.template) if fname
        ]

    def format_prompt(self, **kwargs):
        """Safely formats the template with provided context."""
        return self.template.format(**kwargs)

    def __str__(self):
        return f"{self.identifier} v{self.version}"
