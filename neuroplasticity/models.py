"""Neuroplasticity: the NeuralModifier install / lifecycle registry.

A NeuralModifier is Are-Self's word for an installed extension bundle.
Bundles live on disk as committed ``neuroplasticity/genomes/<slug>.zip``
archives (manifest.json, modifier_data.json, code/, README.md inside
the zip). At install time, the zip is extracted into
``neuroplasticity/grafts/<slug>/`` (the runtime tree) and its
``modifier_data.json`` is loaded into the DB — each row stamped with a
``genome`` FK back to the installing ``NeuralModifier`` row.

This app is the source of truth for *which* modifiers are installed
and the audit trail of install / enable / disable events. Ownership of
individual rows lives on the rows themselves (``genome`` FK from
``GenomeOwnedMixin``), not in a side-car table.
"""

from typing import Optional

from django.db import models

from common.constants import STANDARD_CHARFIELD_LENGTH
from common.models import CreatedMixin, DefaultFieldsMixin, NameMixin


class NeuralModifierStatus(NameMixin):
    """Lifecycle states for a NeuralModifier.

    State machine::

        AVAILABLE -> INSTALLED -> ENABLED <-> DISABLED
        (zip on                     |            |
         disk,                      +------------+---> BROKEN
         no row)                                       ^
             ^                                         | boot-time
             |                                         | drift or
             +-------- uninstall (deletes row) --------+ load failure

    AVAILABLE:  ``genomes/<slug>.zip`` exists and no DB row exists. Not
        a row state — the absence of a row IS the state.
    INSTALLED:  manifest validated, modifier_data.json loaded,
        contributions recorded, code on sys.path. Not yet wired into MCP.
    ENABLED:    INSTALLED plus actively contributing to the MCP tool-set
        builder and live tool resolution.
    DISABLED:   INSTALLED but skipped by the MCP builder. Code still on
        sys.path, contributions still in DB. Reversible via ENABLE.
    BROKEN:     Error state surfaced by the boot re-check or an upgrade
        failure. Manifest hash mismatch against the runtime tree, or
        entry-module import failure. Requires manual intervention.
        (A failed fresh install deletes the row entirely; it does not
        leave a BROKEN row behind.)

    DISCOVERED is retired. The enum value (1) is preserved for
    backwards compatibility with historical log events but is never
    assigned to a new row.
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

    One row per bundle currently in ``grafts/``. The `slug` is the
    stable identifier matching the on-disk directory name; `name` (from
    NameMixin) is the human-readable display name mirrored from the
    manifest at install time. `manifest_json` caches the full manifest
    so routine reads never touch disk; `manifest_hash` is the sha256 of
    manifest.json captured at install, checked on boot to detect
    tampering or version drift.

    Uninstall DELETES the row (AVAILABLE = zip exists + no row).
    Every bundle-owned row (``genome`` FK to this ``NeuralModifier``)
    CASCADEs away, as do installation logs and their events. The
    committed ``genomes/<slug>.zip`` stays put — it is the bundle, not
    a derivative.
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
