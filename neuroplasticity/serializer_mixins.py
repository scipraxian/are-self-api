"""DRF serializer mixins for ``GenomeOwnedMixin`` rows.

These belong on the API surface of every owned model so the frontend
can show "this row is in bundle X" without a second round-trip and so
that creates land in the user's currently-selected workspace bundle
without the request body needing to repeat it.

* ``GenomeDisplayMixin`` — adds a read-only ``genome_slug`` mirror of
  the ``genome`` FK. Pure display; no write side. Safe to layer onto
  any serializer whose ``Meta.model`` carries ``GenomeOwnedMixin``.

* ``GenomeOwnedSerializerMixin`` — defaults the ``genome`` FK on
  ``create()`` to whichever ``NeuralModifier`` is currently
  ``selected_for_edit=True``, falling back to ``INCUBATOR`` when no
  bundle is selected. The request body can still pin a specific
  genome explicitly; that wins. Apply to every ``ModelViewSet``
  serializer that supports CREATE for an owned model.
"""

from __future__ import annotations

from rest_framework import serializers

from neuroplasticity.models import NeuralModifier


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
