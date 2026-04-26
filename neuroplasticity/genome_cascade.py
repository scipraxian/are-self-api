"""Pathway-rooted genome cascade.

Triggered from the BEGIN_PLAY neuron's details panel: the user picks a
bundle (or "None" to clear) and the assignment cascades through the
pathway's compositional reach. Reach traversal lives in
:mod:`neuroplasticity.graph_walker` — this module is just the policy
and the transactional stamp pass.

The walker steps through both ``GenomeOwnedMixin`` rows and the
declared transit models (Neuron, Axon, NeuronContext). The stamping
pass writes the ``genome`` FK only on ``GenomeOwnedMixin`` rows;
transit rows show up in reach but are not stamped — they have no
``genome`` field and their bundle membership is inferred transitively
through their ``pathway`` FK.

The cascade is **additive, not exclusive**:

    * Rows with ``genome=INCUBATOR`` (user workspace) are claimed and
      stamped.
    * Rows already owned by the target genome are unchanged.
    * Rows owned by ``canonical`` are skipped silently — they're
      shared infrastructure (the fixture-shipped ProjectEnvironment a
      pathway points at, etc.); every bundle can reference them, no
      bundle owns them.
    * Rows owned by a different non-canonical genome are also skipped
      silently — cross-bundle references are a feature; the cascade
      doesn't claim another bundle's atoms.
    * Refusal fires only when the **starting pathway itself** is
      canonical-owned. Bundles can't claim core pathways.

Clearing (``target=None``):

    * No-op if the pathway is already ``genome=INCUBATOR``.
    * Otherwise reverts rows in reach that match the pathway's current
      bundle back to ``INCUBATOR``. Rows owned by canonical or by
      other bundles are left alone; the cascade only undoes its own
      prior work.

Refused operations rollback via ``transaction.atomic``; partial stamps
do not land.
"""

from __future__ import annotations

from typing import List, Optional

from django.db import transaction

from neuroplasticity.genome_mixin import GenomeOwnedMixin
from neuroplasticity.graph_walker import walk_genome_reach
from neuroplasticity.models import NeuralModifier


def _display_name(instance) -> str:
    name = getattr(instance, 'name', None)
    if name:
        return str(name)
    return str(instance)


def _slug_for_pk(pk) -> Optional[str]:
    if pk is None:
        return None
    return (
        NeuralModifier.objects.filter(pk=pk)
        .values_list('slug', flat=True)
        .first()
    )


def _conflict_descriptor(row, owner_slug: Optional[str]) -> dict:
    return {
        'app_label': type(row)._meta.app_label,
        'model': type(row)._meta.model_name,
        'pk': str(row.pk),
        'name_or_repr': _display_name(row),
        'owned_by': owner_slug,
    }


def _pathway_reach(pathway):
    """Reach for a pathway: the pathway plus its compositional content.

    Reverse-FK descent to transit models is enabled for
    ``NeuralPathway`` only — the walker descends from a pathway to its
    Neurons and Axons but does not later reverse-walk from an Effector
    back to other Neurons in neighbouring user content.
    """
    # Local import to avoid AppConfig boot-time circulars.
    from central_nervous_system.models import NeuralPathway
    return walk_genome_reach(
        [pathway],
        reverse_fk=True,
        transit_reverse_fk_sources=(NeuralPathway,),
    )


class GenomeCascadeConflict(Exception):
    """The starting pathway is canonical-owned and can't be claimed."""

    def __init__(self, conflicts: List[dict]):
        self.conflicts = conflicts
        super().__init__(
            '[Neuroplasticity] Cascade refused - the pathway is owned '
            'by canonical and cannot be claimed by a bundle.'
        )


@transaction.atomic
def cascade_pathway_genome(
    pathway, target_modifier: Optional[NeuralModifier]
) -> dict:
    """Stamp ``target_modifier`` on the pathway and the reachable
    GenomeOwnedMixin rows it composes. Pass ``None`` to clear back to
    INCUBATOR.

    Stamp (``target_modifier`` not None):
        * Claims ``genome=INCUBATOR`` rows in reach for
          ``target_modifier``.
        * Skips rows owned by canonical or by another bundle (those
          are shared infrastructure / cross-bundle references; the
          cascade doesn't claim them).
        * Refuses only when the starting pathway itself is canonical.

    Clear (``target_modifier`` is None):
        * No-op if the pathway is already ``genome=INCUBATOR``.
        * Otherwise reverts rows in reach that match the pathway's
          current bundle back to INCUBATOR. Canonical and
          cross-bundle rows are left alone.

    Returns::

        {
          'pathway_id': str,
          'target_slug': str | None,
          'stamped': int,    # rows the cascade wrote to
          'unchanged': int,  # rows in reach that weren't written
          'skipped': int,    # rows skipped because they're owned by
                             # canonical or another bundle
          'rows': [{app_label, model, pk, name_or_repr,
                    previous_owner_slug | None}],
        }

    Raises:
        GenomeCascadeConflict: the starting pathway is canonical-owned.
    """
    target_pk = target_modifier.pk if target_modifier is not None else None
    target_slug = (
        target_modifier.slug if target_modifier is not None else None
    )

    # The only refusal: the user is trying to claim a canonical pathway
    # for their bundle. Everything else (cross-bundle references,
    # canonical infrastructure in reach) is fine — the cascade is
    # additive.
    if pathway.genome_id == NeuralModifier.CANONICAL:
        raise GenomeCascadeConflict(
            [_conflict_descriptor(pathway, 'canonical')]
        )

    # Reach includes transit rows (Neuron / Axon / NeuronContext);
    # filter to GenomeOwnedMixin only — those are the rows that carry
    # a `genome` FK we can write to.
    bundle_rows = [
        r for r in _pathway_reach(pathway) if isinstance(r, GenomeOwnedMixin)
    ]

    stamped = 0
    unchanged = 0
    skipped = 0
    touched: List[dict] = []

    if target_modifier is None:
        # Clear mode: revert rows owned by the pathway's current bundle
        # back to INCUBATOR.
        prior_bundle_pk = pathway.genome_id
        if prior_bundle_pk == NeuralModifier.INCUBATOR:
            return {
                'pathway_id': str(pathway.pk),
                'target_slug': None,
                'stamped': 0,
                'unchanged': len(bundle_rows),
                'skipped': 0,
                'rows': [],
            }
        for row in bundle_rows:
            if row.genome_id == prior_bundle_pk:
                row.genome_id = NeuralModifier.INCUBATOR
                row.save(update_fields=['genome'])
                stamped += 1
                touched.append(
                    {
                        'app_label': type(row)._meta.app_label,
                        'model': type(row)._meta.model_name,
                        'pk': str(row.pk),
                        'name_or_repr': _display_name(row),
                        'previous_owner_slug': _slug_for_pk(prior_bundle_pk),
                    }
                )
            elif row.genome_id == NeuralModifier.INCUBATOR:
                unchanged += 1
            else:
                # Owned by canonical or another bundle — left alone.
                skipped += 1
        return {
            'pathway_id': str(pathway.pk),
            'target_slug': None,
            'stamped': stamped,
            'unchanged': unchanged,
            'skipped': skipped,
            'rows': touched,
        }

    # Stamp mode: claim INCUBATOR rows for target; skip everyone else's.
    for row in bundle_rows:
        current_pk = row.genome_id
        if current_pk == target_pk:
            unchanged += 1
            continue
        if current_pk == NeuralModifier.INCUBATOR:
            row.genome_id = target_pk
            row.save(update_fields=['genome'])
            stamped += 1
            touched.append(
                {
                    'app_label': type(row)._meta.app_label,
                    'model': type(row)._meta.model_name,
                    'pk': str(row.pk),
                    'name_or_repr': _display_name(row),
                    'previous_owner_slug': NeuralModifier.INCUBATOR_SLUG,
                }
            )
            continue
        # Owned by canonical or another bundle — skip silently.
        skipped += 1

    return {
        'pathway_id': str(pathway.pk),
        'target_slug': target_slug,
        'stamped': stamped,
        'unchanged': unchanged,
        'skipped': skipped,
        'rows': touched,
    }


# Backward-compat shim: callers that imported reachable_genome_rows
# from this module pre-consolidation. Same semantics as
# walk_genome_reach with the pathway-source transit rule.
def reachable_genome_rows(pathway) -> List:
    return _pathway_reach(pathway)
