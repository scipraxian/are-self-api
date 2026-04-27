"""DRF serializer + viewset mixins for ``GenomeOwnedMixin`` rows.

These belong on the API surface of every owned model so the frontend
can show "this row is in bundle X" without a second round-trip, so
that creates land in the user's currently-selected workspace bundle
without the request body needing to repeat it, and so that PATCHing
``genome`` promotes a row from INCUBATOR into a target bundle with the
same coordinated-restart semantics as install / uninstall.

* ``GenomeDisplayMixin`` — read-only ``genome_slug`` mirror of the
  ``genome`` FK. Pure display; no write side. Safe to layer onto any
  serializer whose ``Meta.model`` carries ``GenomeOwnedMixin``.

* ``GenomeOwnedSerializerMixin`` — defaults the ``genome`` FK on
  ``create()`` to whichever ``NeuralModifier`` is currently
  ``selected_for_edit=True``, falling back to ``INCUBATOR`` when no
  bundle is selected. Explicit ``genome`` in the body wins.

* ``GenomeWritableMixin`` — makes ``genome`` writable on a V2
  serializer with canonical-refusal rules. Layers next to
  ``GenomeDisplayMixin`` and ``GenomeOwnedSerializerMixin``. Refuses
  PATCHes that would move a row into canonical, out of canonical, or
  into a non-INSTALLED target.

* ``GenomeMoveRestartMixin`` — viewset ``partial_update`` override
  that triggers the standard system restart whenever a PATCH actually
  changes ``genome_id``. No-op when the value did not change.
"""

from __future__ import annotations

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from neuroplasticity.models import NeuralModifier, NeuralModifierStatus
from peripheral_nervous_system.autonomic_nervous_system import (
    trigger_system_restart,
)


GENOME_INTO_CANONICAL_REFUSAL = (
    'Cannot promote into canonical: canonical is read-only and git-managed.'
)
GENOME_OUT_OF_CANONICAL_REFUSAL = (
    'Cannot move a canonical row: canonical is read-only and git-managed.'
)
GENOME_NOT_INSTALLED_REFUSAL = 'Target genome is not an INSTALLED bundle.'


class GenomeDisplayMixin(serializers.Serializer):
    """Read-only ``genome_slug`` companion to the ``genome`` FK."""

    genome_slug = serializers.CharField(
        source='genome.slug', read_only=True, default=None
    )


class GenomeOwnedSerializerMixin(serializers.Serializer):
    """Stamp the active workspace genome on create when the body omits one.

    Selected bundle wins; fall back to ``INCUBATOR`` if no bundle is
    flagged. Explicit ``genome`` in the request body always wins. The
    DRF ``ModelSerializer`` keys an incoming FK by field name (here
    ``'genome'``); the mixin also tolerates ``'genome_id'`` so a
    serializer using ``PrimaryKeyRelatedField(source='genome', ...)``
    composes cleanly.
    """

    def create(self, validated_data):
        if (
            'genome' not in validated_data
            and 'genome_id' not in validated_data
        ):
            selected = NeuralModifier.objects.filter(
                selected_for_edit=True
            ).only('id').first()
            validated_data['genome_id'] = (
                selected.id if selected is not None else NeuralModifier.INCUBATOR
            )
        return super().create(validated_data)


class GenomeWritableMixin(serializers.Serializer):
    """Make ``genome`` writable on a V2 serializer with canonical refusal.

    Layers next to ``GenomeDisplayMixin`` (read-only ``genome_slug``)
    and ``GenomeOwnedSerializerMixin`` (default-on-create). This one
    governs PATCH: the field accepts a ``NeuralModifier`` UUID, refuses
    canonical in either direction, and refuses targets that are not
    INSTALLED. The companion ``GenomeMoveRestartMixin`` on the viewset
    fires the coordinated restart when a PATCH actually changes
    ``genome_id``.
    """

    def validate_genome(self, value):
        if value is None:
            return value
        if value.pk == NeuralModifier.CANONICAL:
            raise ValidationError(GENOME_INTO_CANONICAL_REFUSAL)
        if value.status_id != NeuralModifierStatus.INSTALLED:
            raise ValidationError(GENOME_NOT_INSTALLED_REFUSAL)
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if (
            self.instance is not None
            and 'genome' in attrs
            and self.instance.genome_id == NeuralModifier.CANONICAL
        ):
            raise ValidationError(
                {'genome': GENOME_OUT_OF_CANONICAL_REFUSAL}
            )
        return attrs


class GenomeMoveRestartMixin(object):
    """Trigger the coordinated restart on PATCHes that change ``genome_id``.

    Captures pre-PATCH ``genome_id`` from the persisted row, runs
    ``super().partial_update()``, then re-reads ``genome_id`` from the
    DB (via ``values_list``, NOT ``refresh_from_db`` — some models'
    ``__init__`` triggers deferred-field loads that recurse on a
    partially-loaded instance). If the two differ, calls
    ``trigger_system_restart()`` and adds ``'restart_imminent': True``
    to ``response.data``. No-op otherwise.
    """

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        model_cls = type(instance)
        old_genome_id = instance.genome_id
        response = super().partial_update(request, *args, **kwargs)
        new_genome_id = model_cls.objects.filter(
            pk=instance.pk,
        ).values_list('genome_id', flat=True).first()
        if new_genome_id != old_genome_id:
            trigger_system_restart()
            if isinstance(response.data, dict):
                response.data['restart_imminent'] = True
        return response
