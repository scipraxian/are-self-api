"""Neuroplasticity: the NeuralModifier install / lifecycle registry.

A NeuralModifier is Are-Self's word for an installed extension bundle.
Bundles live on disk at `neural_modifiers/{slug}/` (manifest.json,
modifier_data.json, code/, README.md) and are immutable post-install.
This app is the source of truth for *which* modifiers are installed,
*what* each one contributed to the database, and the audit trail of
install / enable / disable events.
"""

from typing import Generator, Optional

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from common.constants import STANDARD_CHARFIELD_LENGTH
from common.models import CreatedMixin, DefaultFieldsMixin, NameMixin


class NeuralModifierStatus(NameMixin):
    """Lifecycle states for a NeuralModifier.

    State machine::

        DISCOVERED -> INSTALLED -> ENABLED <-> DISABLED
                          |           |           |
                          +-----------+-----------+--> BROKEN

    DISCOVERED: `neural_modifiers/{slug}/` exists and manifest parsed, but
        modifier_data.json has not been loaded and code is not on sys.path.
    INSTALLED:  manifest validated, modifier_data.json loaded, contributions
        recorded, code available for import. Not yet wired into MCP.
    ENABLED:    INSTALLED plus actively contributing to the MCP tool-set
        builder and live tool resolution.
    DISABLED:   INSTALLED but skipped by the MCP builder. Code still on
        sys.path, contributions still in DB. Reversible via ENABLE.
    BROKEN:     Terminal error state. Manifest hash mismatch, missing
        dependency, load failure, or crash mid-install / mid-uninstall.
        Requires manual intervention.
    """

    DISCOVERED = 1
    INSTALLED = 2
    ENABLED = 3
    DISABLED = 4
    BROKEN = 5

    class Meta:
        verbose_name = 'Neural Modifier Status'
        verbose_name_plural = 'Neural Modifier Statuses'


class NeuralModifier(DefaultFieldsMixin):
    """An installed NeuralModifier bundle registered with the running system.

    One row per bundle in `neural_modifiers/`. The `slug` is the stable
    identifier matching the on-disk directory name; `name` (from
    NameMixin) is the human-readable display name mirrored from the
    manifest at install time. `manifest_json` caches the full manifest
    so routine reads never touch disk; `manifest_hash` is the sha256 of
    manifest.json captured at install, checked on boot to detect
    tampering or version drift.

    NeuralModifier rows are never deleted on uninstall — status flips to
    DISCOVERED (or BROKEN) and the installation log history is retained.
    """

    status = models.ForeignKey(
        NeuralModifierStatus, on_delete=models.CASCADE
    )
    slug = models.SlugField(unique=True)
    version = models.CharField(max_length=STANDARD_CHARFIELD_LENGTH)
    author = models.CharField(max_length=STANDARD_CHARFIELD_LENGTH)
    license = models.CharField(max_length=STANDARD_CHARFIELD_LENGTH)
    manifest_hash = models.CharField(max_length=STANDARD_CHARFIELD_LENGTH)
    manifest_json = models.JSONField()

    class Meta:
        verbose_name = 'Neural Modifier'
        verbose_name_plural = 'Neural Modifiers'

    def current_installation(
        self,
    ) -> Optional['NeuralModifierInstallationLog']:
        """Return the most recent installation log, or None if never installed.

        Uninstall replays the frozen manifest from this row; callers must
        never reach past it to an older log.
        """
        return self.installation_logs.order_by('-created').first()

    def iter_contributed_objects(self) -> Generator[models.Model, None, None]:
        """Yield each live DB object this modifier created, in install order.

        Used during uninstall to walk contribution targets before deletion.
        Orphaned contributions (target already deleted out from under us)
        are skipped silently; detect them by comparing the yielded count
        against `self.contributions.count()`.
        """
        contributions = self.contributions.order_by('created')
        for contribution in contributions:
            target = contribution.content_object
            if target is not None:
                yield target


class NeuralModifierContribution(CreatedMixin):
    """One row per DB object a NeuralModifier created on install.

    This is the uninstall manifest in table form. When a modifier's
    modifier_data.json loads and creates an Effector, NeuralPathway,
    ContextVariable, etc., a Contribution row is written pointing at it
    via GenericForeignKey. Uninstall iterates these rows, deletes each
    target, then deletes the contribution rows themselves.

    The `object_id` column is a UUIDField because every
    NeuralModifier-extensible model in Are-Self was migrated to UUID
    primary keys in the Pass 1 `uuid-migration` branch — that migration
    is the prerequisite for this table existing at all. Protocol enums
    (SpikeStatus, AxonType, etc.) stayed integer-keyed and are never
    contribution targets.
    """

    neural_modifier = models.ForeignKey(
        NeuralModifier,
        on_delete=models.CASCADE,
        related_name='contributions',
    )
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE
    )
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        verbose_name = 'Neural Modifier Contribution'
        verbose_name_plural = 'Neural Modifier Contributions'
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return '{modifier} -> {ct} {pk}'.format(
            modifier=self.neural_modifier.name,
            ct=self.content_type,
            pk=self.object_id,
        )


class NeuralModifierInstallationLog(CreatedMixin):
    """One row per install attempt against a NeuralModifier.

    Reinstalling a modifier creates a new log row rather than updating
    the old one, so the full history is preserved. `installation_manifest`
    is a frozen snapshot of the manifest at that install's moment —
    useful for debugging version-drift issues where the on-disk manifest
    has since been replaced.

    Events for a given install attempt hang off this row, not directly
    off NeuralModifier, so event streams stay cleanly partitioned per
    install session.
    """

    neural_modifier = models.ForeignKey(
        NeuralModifier,
        on_delete=models.CASCADE,
        related_name='installation_logs',
    )
    installation_manifest = models.JSONField()

    class Meta:
        verbose_name = 'Neural Modifier Installation Log'
        verbose_name_plural = 'Neural Modifier Installation Logs'
        ordering = ['-created']


class NeuralModifierInstallationEventType(NameMixin):
    """Event type lookups for NeuralModifierInstallationEvent."""

    INSTALL = 1
    UNINSTALL = 2
    ENABLE = 3
    DISABLE = 4
    LOAD_FAILED = 5
    HASH_MISMATCH = 6
    UPGRADE = 7

    class Meta:
        verbose_name = 'Neural Modifier Installation Event Type'
        verbose_name_plural = 'Neural Modifier Installation Event Types'


class NeuralModifierInstallationEvent(CreatedMixin):
    """A single step within a NeuralModifierInstallationLog.

    Append-only. Captures the blow-by-blow of an install / uninstall /
    enable / disable so post-mortem debugging doesn't require re-running
    the offending operation. `event_data` is free-form JSON: stack
    traces for failures, file lists for successes, whatever the handler
    wants to stash.
    """

    neural_modifier_installation_log = models.ForeignKey(
        NeuralModifierInstallationLog,
        on_delete=models.CASCADE,
        related_name='events',
    )
    event_type = models.ForeignKey(
        NeuralModifierInstallationEventType, on_delete=models.CASCADE
    )
    event_data = models.JSONField()

    class Meta:
        verbose_name = 'Neural Modifier Installation Event'
        verbose_name_plural = 'Neural Modifier Installation Events'
        ordering = ['created']
