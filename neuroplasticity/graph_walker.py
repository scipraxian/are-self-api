"""Forward-FK walker for the bundle-builder UI.

Starting from every row a bundle owns (``genome__slug=<slug>``),
walks forward FKs and M2M relations whose target model also carries
``GenomeOwnedMixin`` (the twelve bundle-eligible models, as registered
with :func:`loader.iter_genome_owned_models`). Anything outside that
set is a boundary — we record the reachable row but do not recurse
past it.

Four diagnostic states are emitted per reachable row:

* ``owned`` — ``genome.slug == <slug>``. Part of this bundle.
* ``shared-with <other_slug>`` — ``genome`` non-null and not this
  bundle. A different bundle already owns it.
* ``orphan`` — ``genome`` is null AND the PK is not in any fixture
  indexed by :mod:`neuroplasticity.fixture_scan`. User forgot to tag
  it; it would be silently lost on Save-to-Genome.
* ``core`` — ``genome`` is null AND the PK IS indexed — legitimately
  shipped in a committed fixture.

Output shape is API-only. If you're tempted to embed HTML, stop —
the UI renders.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set, Tuple

from neuroplasticity import loader
from neuroplasticity.fixture_scan import get_fixture_pk_index
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


def _forward_fk_fields(model: type) -> Iterable:
    """Concrete FK fields on ``model`` whose target is also GenomeOwnedMixin."""
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
        if not issubclass(related, GenomeOwnedMixin):
            continue
        # Exclude the genome FK itself — it points at NeuralModifier,
        # not at one of the 12 bundle-eligible models.
        if field.name == 'genome':
            continue
        yield field


def _forward_m2m_fields(model: type) -> Iterable:
    """Concrete forward M2M fields whose target is GenomeOwnedMixin."""
    for field in model._meta.get_fields():
        if not getattr(field, 'many_to_many', False):
            continue
        if not getattr(field, 'concrete', False):
            continue
        related = field.related_model
        if related is None:
            continue
        if not issubclass(related, GenomeOwnedMixin):
            continue
        yield field


def _classify(instance, target_slug: str, fixture_index: Dict[str, Set[str]]):
    """Return (state, owner_slug) for one row."""
    genome = getattr(instance, 'genome', None)
    if genome is None:
        model_key = '{0}.{1}'.format(
            type(instance)._meta.app_label,
            type(instance)._meta.model_name,
        )
        if str(instance.pk) in fixture_index.get(model_key, set()):
            return ('core', None)
        return ('orphan', None)
    owner_slug = genome.slug
    if owner_slug == target_slug:
        return ('owned', owner_slug)
    return ('shared-with {0}'.format(owner_slug), owner_slug)


def build_bundle_graph(slug: str) -> dict:
    """Return the ✓/X/?/ⓘ state tree for the Modifier Garden builder.

    Shape::

        {
          'slug': str,
          'nodes': [
            {
              'app_label': str,
              'model': str,
              'pk': str,
              'name_or_repr': str,
              'state': str,            # 'owned' | 'shared-with X'
                                       # | 'orphan' | 'core'
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
    """
    modifier = NeuralModifier.objects.get(slug=slug)
    fixture_index = get_fixture_pk_index()

    visited: Dict[Tuple[str, str, str], Any] = {}
    edges: List[dict] = []
    queue: List[Any] = []

    for model in loader.iter_genome_owned_models():
        for instance in model.objects.filter(genome=modifier):
            key = _row_key(model, instance.pk)
            if key not in visited:
                visited[key] = instance
                queue.append(instance)

    while queue:
        instance = queue.pop(0)
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
            target_model = type(target)
            target_key = _row_key(target_model, target.pk)
            if target_key not in visited:
                visited[target_key] = target
                queue.append(target)
            edges.append(
                {
                    'source': src_label,
                    'target': {
                        'app_label': target_model._meta.app_label,
                        'model': target_model._meta.model_name,
                        'pk': str(target.pk),
                    },
                    'via': field.name,
                    'kind': 'fk',
                }
            )

        for field in _forward_m2m_fields(src_model):
            manager = getattr(instance, field.name)
            for target in manager.all():
                target_model = type(target)
                target_key = _row_key(target_model, target.pk)
                if target_key not in visited:
                    visited[target_key] = target
                    queue.append(target)
                edges.append(
                    {
                        'source': src_label,
                        'target': {
                            'app_label': target_model._meta.app_label,
                            'model': target_model._meta.model_name,
                            'pk': str(target.pk),
                        },
                        'via': field.name,
                        'kind': 'm2m',
                    }
                )

    nodes: List[dict] = []
    for (app_label, model_name, pk), instance in visited.items():
        state, owner_slug = _classify(instance, slug, fixture_index)
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
