"""Forward / reverse FK walker over the bundle ownership graph.

Two callers share the traversal logic in this module:

* ``build_genome_graph(slug)`` — read-only diagnostic graph for the
  Modifier Garden UI. Starts from every row a bundle owns
  (``genome__slug=<slug>``) and walks forward FKs and forward M2M
  relations to other ``GenomeOwnedMixin`` rows. Reverse-FK is not
  needed in read mode because every owned row is already a starting
  point — reverse-FK reach is redundant.

* ``walk_genome_reach(starts, *, reverse_fk=False)`` — general-purpose
  visit walker used by the cascade (write-stamp). Starts from a small
  seed set and walks forward FK / M2M; with ``reverse_fk=True`` it
  also walks reverse-FK to ``GenomeOwnedMixin`` targets.

Reach traversal rules:

    * Forward FK / M2M: traverse if the target model inherits
      ``GenomeOwnedMixin`` (every bundle-extensible model carries the
      mixin, including the former transit models Neuron / Axon /
      NeuronContext).
    * Reverse FK to ``GenomeOwnedMixin``: traversed when
      ``reverse_fk=True``. These are the source row's owned children
      (e.g. NeuralPathway → its Neurons; Effector → its
      ArgumentAssignments).
    * The ``genome`` FK itself is never followed — it points at
      ``NeuralModifier``, not at a bundle-eligible model.

Four diagnostic states are emitted by ``build_genome_graph`` per
reachable row, keyed off the three-state Canonical Genome model:

* ``canonical`` — ``genome_id == NeuralModifier.CANONICAL``. Ships in
  a committed core fixture; never deleted by any bundle operation.
* ``owned`` — ``genome.slug == <target_slug>``. Part of this bundle.
* ``shared-with <other_slug>`` — ``genome`` points at another bundle.
* ``user`` — ``genome_id == NeuralModifier.INCUBATOR``. Created by
  the user at runtime in the default workspace; bundles must not
  touch it.

Output shape is API-only. If you're tempted to embed HTML, stop —
the UI renders.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Sequence, Tuple

from neuroplasticity import loader
from neuroplasticity.genome_mixin import GenomeOwnedMixin
from neuroplasticity.models import NeuralModifier


def _row_key(model: type, pk: Any) -> Tuple[str, str, str]:
    """Stable (app_label, model, pk) triple used as visit key."""
    return (model._meta.app_label, model._meta.model_name, str(pk))


def _display_name(instance) -> str:
    """Best-effort human label for a row — ``name`` if available else repr."""
    name = getattr(instance, 'name', None)
    if name:
        return str(name)
    return str(instance)


def _is_walkable_target(model: type) -> bool:
    """The walker steps to a target iff it carries ``GenomeOwnedMixin``."""
    return issubclass(model, GenomeOwnedMixin)


def _forward_fk_fields(model: type) -> Iterable:
    """Concrete forward FK fields whose target is walkable."""
    for field in model._meta.get_fields():
        if not getattr(field, 'is_relation', False):
            continue
        if not getattr(field, 'many_to_one', False):
            continue
        if not getattr(field, 'concrete', False):
            continue
        related = field.related_model
        if related is None:
            continue
        if not _is_walkable_target(related):
            continue
        # Exclude the genome FK itself — it points at NeuralModifier,
        # not at a bundle-eligible model.
        if field.name == 'genome':
            continue
        yield field


def _forward_m2m_fields(model: type) -> Iterable:
    """Concrete forward M2M fields whose target is walkable."""
    for field in model._meta.get_fields():
        if not getattr(field, 'many_to_many', False):
            continue
        if not getattr(field, 'concrete', False):
            continue
        related = field.related_model
        if related is None:
            continue
        if not _is_walkable_target(related):
            continue
        yield field


def _reverse_fk_fields(model: type) -> Iterable[Tuple[Any, str]]:
    """Reverse one-to-many fields whose target is ``GenomeOwnedMixin``.

    Each yield is ``(field, accessor_name)`` so the caller can fetch
    via ``getattr(instance, accessor)``.
    """
    for field in model._meta.get_fields():
        if not getattr(field, 'is_relation', False):
            continue
        if not getattr(field, 'one_to_many', False):
            continue
        if getattr(field, 'concrete', False):
            # one_to_many concrete is unusual; the standard reverse
            # accessor is non-concrete (ManyToOneRel).
            continue
        related = field.related_model
        if related is None:
            continue
        if not issubclass(related, GenomeOwnedMixin):
            continue
        accessor = field.get_accessor_name()
        if accessor is None:
            continue
        yield field, accessor


def walk_genome_reach(
    starts: Sequence[Any],
    *,
    reverse_fk: bool = False,
) -> List[Any]:
    """BFS from ``starts`` through the bundle reach graph.

    Forward FK / M2M traversal is unconditional to ``GenomeOwnedMixin``
    targets. Reverse-FK traversal is OFF by default (read-mode
    behaviour — every owned row is already a starting point so
    reverse-FK reach is redundant). When ``reverse_fk=True``, the
    walker also traverses reverse-FK to ``GenomeOwnedMixin`` targets,
    so reach descends from a parent (e.g. NeuralPathway) to its
    children (e.g. Neurons / Axons).

    Returns the visited list (insertion-ordered, includes the starts).
    Caller filters / classifies as needed.
    """
    visited: dict = {}
    queue: List[Any] = []

    def enqueue(inst) -> None:
        if inst is None:
            return
        key = _row_key(type(inst), inst.pk)
        if key not in visited:
            visited[key] = inst
            queue.append(inst)

    for start in starts:
        enqueue(start)

    while queue:
        instance = queue.pop(0)
        src_model = type(instance)

        for field in _forward_fk_fields(src_model):
            try:
                target = getattr(instance, field.name)
            except field.related_model.DoesNotExist:
                target = None
            enqueue(target)

        for field in _forward_m2m_fields(src_model):
            manager = getattr(instance, field.name)
            for target in manager.all():
                enqueue(target)

        if not reverse_fk:
            continue

        for field, accessor in _reverse_fk_fields(src_model):
            try:
                manager = getattr(instance, accessor)
            except AttributeError:
                continue
            for target in manager.all():
                enqueue(target)

    return list(visited.values())


def _classify(instance, target_slug: str):
    """Return (state, owner_slug) for one row under the three-state model."""
    genome_id = getattr(instance, 'genome_id', None)
    if genome_id == NeuralModifier.INCUBATOR:
        return ('user', None)
    if genome_id == NeuralModifier.CANONICAL:
        return ('canonical', NeuralModifier.CANONICAL_SLUG)
    # genome_id points at a real bundle — dereference the slug. The
    # FK object may already be prefetched; fall back to a cheap
    # values_list lookup otherwise.
    genome = getattr(instance, 'genome', None)
    owner_slug = getattr(genome, 'slug', None)
    if owner_slug is None:
        owner_slug = (
            NeuralModifier.objects.filter(pk=genome_id)
            .values_list('slug', flat=True)
            .first()
        )
    if owner_slug == target_slug:
        return ('owned', owner_slug)
    return ('shared-with {0}'.format(owner_slug), owner_slug)


def build_genome_graph(slug: str) -> dict:
    """Return the state tree for the Modifier Garden builder.

    Shape::

        {
          'slug': str,
          'nodes': [
            {
              'app_label': str,
              'model': str,
              'pk': str,
              'name_or_repr': str,
              'state': str,            # 'canonical' | 'owned'
                                       # | 'shared-with X' | 'user'
              'owner_slug': str | None,
            },
            ...
          ],
          'edges': [
            {
              'source': {app_label, model, pk},
              'target': {app_label, model, pk},
              'via': str,              # field name on source
              'kind': 'fk' | 'm2m',
            },
            ...
          ],
        }

    Read-only mode: every owned row is a start, so reverse-FK reach
    is not needed (would just rediscover starts). Only forward FK and
    M2M edges are emitted; the walker behaviour matches the original
    forward-only diagnostic build.
    """
    modifier = NeuralModifier.objects.get(slug=slug)

    starts: List[Any] = []
    for model in loader.iter_genome_owned_models():
        starts.extend(model.objects.filter(genome=modifier))

    # Visit walk first (forward only — no transit reverse-FK sources)
    # so we have the full visited set; then derive forward-edge list
    # from the visit set the same way the original walker did.
    visited_list = walk_genome_reach(starts)
    visited: dict = {
        _row_key(type(inst), inst.pk): inst for inst in visited_list
    }

    edges: List[dict] = []
    for instance in visited_list:
        src_model = type(instance)
        src_label = {
            'app_label': src_model._meta.app_label,
            'model': src_model._meta.model_name,
            'pk': str(instance.pk),
        }
        for field in _forward_fk_fields(src_model):
            try:
                target = getattr(instance, field.name)
            except field.related_model.DoesNotExist:
                target = None
            if target is None:
                continue
            target_key = _row_key(type(target), target.pk)
            if target_key not in visited:
                continue
            edges.append(
                {
                    'source': src_label,
                    'target': {
                        'app_label': type(target)._meta.app_label,
                        'model': type(target)._meta.model_name,
                        'pk': str(target.pk),
                    },
                    'via': field.name,
                    'kind': 'fk',
                }
            )
        for field in _forward_m2m_fields(src_model):
            manager = getattr(instance, field.name)
            for target in manager.all():
                target_key = _row_key(type(target), target.pk)
                if target_key not in visited:
                    continue
                edges.append(
                    {
                        'source': src_label,
                        'target': {
                            'app_label': type(target)._meta.app_label,
                            'model': type(target)._meta.model_name,
                            'pk': str(target.pk),
                        },
                        'via': field.name,
                        'kind': 'm2m',
                    }
                )

    nodes: List[dict] = []
    for (app_label, model_name, pk), instance in visited.items():
        state, owner_slug = _classify(instance, slug)
        nodes.append(
            {
                'app_label': app_label,
                'model': model_name,
                'pk': pk,
                'name_or_repr': _display_name(instance),
                'state': state,
                'owner_slug': owner_slug,
            }
        )

    nodes.sort(key=lambda n: (n['app_label'], n['model'], n['pk']))

    return {
        'slug': slug,
        'nodes': nodes,
        'edges': edges,
    }
