"""
Synchronous memory operations for mcp_memory (testable, no async).
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from django.db.models import QuerySet
from pgvector.django import CosineDistance

from frontal_lobe.synapse import OllamaClient
from hippocampus.models import Engram, EngramTag

logger = logging.getLogger(__name__)

HERMES_MEMORY_TAG = 'hermes_memory'
MAX_ENTRY_CHARS = 400
MAX_TOTAL_CHARS = 2000
SIMILARITY_CUTOFF = 0.90


def _normalize_collection(raw: str) -> str:
    c = raw.strip().lower()
    if c in ('agent_memory', 'user_profile'):
        return c
    raise ValueError(
        'collection must be agent_memory or user_profile.',
    )


def _collection_tags(collection: str) -> Tuple[str, ...]:
    return (collection, HERMES_MEMORY_TAG)


def _ensure_tags(names: Tuple[str, ...]) -> List[EngramTag]:
    out = []
    for name in names:
        tag, _ = EngramTag.objects.get_or_create(name=name)
        out.append(tag)
    return out


def _tagged_active_engrams(collection: str) -> QuerySet:
    """Return active Engrams tagged for the collection and hermes_memory."""
    tags = _ensure_tags(_collection_tags(collection))
    qs = Engram.objects.filter(is_active=True)
    for t in tags:
        qs = qs.filter(tags=t)
    return qs.distinct()


def _total_chars(collection: str) -> int:
    total = 0
    for row in _tagged_active_engrams(collection).values_list(
        'description',
        flat=True,
    ):
        total += len(row or '')
    return total


def _count_entries(collection: str) -> int:
    return _tagged_active_engrams(collection).count()


def _embed_text(text: str) -> List[float]:
    client = OllamaClient('nomic-embed-text')
    return client.embed(text)


def run_memory_action(
    action: str,
    collection: str,
    content: str,
    old_content: str,
    new_content: str,
    content_snippet: str,
    session_id: str,
    turn_id: str,
) -> Dict[str, Any]:
    """Dispatch add / replace / remove."""
    act = action.strip().lower()
    coll = _normalize_collection(collection)

    if act == 'add':
        return _memory_add(coll, content, session_id, turn_id)
    if act == 'replace':
        return _memory_replace(coll, old_content, new_content, session_id, turn_id)
    if act == 'remove':
        return _memory_remove(coll, content_snippet, session_id, turn_id)
    raise ValueError('action must be add, replace, or remove.')


def _memory_add(
    collection: str,
    content: str,
    session_id: str,
    turn_id: str,
) -> Dict[str, Any]:
    if not content or not content.strip():
        raise ValueError('content is required for add.')
    if len(content) > MAX_ENTRY_CHARS:
        raise ValueError(
            'content exceeds %s characters.' % MAX_ENTRY_CHARS,
        )
    if _total_chars(collection) + len(content) > MAX_TOTAL_CHARS:
        raise ValueError(
            'Collection total would exceed %s characters.' % MAX_TOTAL_CHARS,
        )

    tags = _ensure_tags(_collection_tags(collection))
    name = content[:80]
    vector = _embed_text(content)
    engram = Engram.objects.create(
        name=name,
        description=content,
        vector=vector,
        is_active=True,
    )
    for t in tags:
        engram.tags.add(t)

    return {
        'collection': collection,
        'action': 'add',
        'entries_count': _count_entries(collection),
        'total_chars': _total_chars(collection),
        'engram_id': str(engram.id),
    }


def _memory_replace(
    collection: str,
    old_content: str,
    new_content: str,
    session_id: str,
    turn_id: str,
) -> Dict[str, Any]:
    if not new_content or not new_content.strip():
        raise ValueError('new_content is required for replace.')
    if len(new_content) > MAX_ENTRY_CHARS:
        raise ValueError(
            'new_content exceeds %s characters.' % MAX_ENTRY_CHARS,
        )

    needle = old_content or ''
    vector = _embed_text(needle) if needle else None
    qs = Engram.objects.filter(is_active=True)
    for tag in _collection_tags(collection):
        qs = qs.filter(tags__name=tag)

    target = None
    if vector:
        scored = (
            qs.exclude(vector__isnull=True)
            .annotate(distance=CosineDistance('vector', vector))
            .order_by('distance')
        )
        if scored.exists():
            best = scored.first()
            similarity = 1.0 - best.distance
            if similarity >= SIMILARITY_CUTOFF:
                target = best

    if target is None and needle:
        for cand in qs:
            if needle in (cand.description or ''):
                target = cand
                break

    if target is None:
        raise ValueError('No matching entry found to replace.')

    delta = len(new_content) - len(target.description or '')
    if _total_chars(collection) + delta > MAX_TOTAL_CHARS:
        raise ValueError(
            'Collection total would exceed %s characters.' % MAX_TOTAL_CHARS,
        )

    target.description = new_content
    target.name = new_content[:80]
    target.vector = _embed_text(new_content)
    target.save(update_fields=['description', 'name', 'vector'])

    return {
        'collection': collection,
        'action': 'replace',
        'entries_count': _count_entries(collection),
        'total_chars': _total_chars(collection),
        'engram_id': str(target.id),
    }


def _memory_remove(
    collection: str,
    content_snippet: str,
    session_id: str,
    turn_id: str,
) -> Dict[str, Any]:
    if not content_snippet or not content_snippet.strip():
        raise ValueError('content_snippet is required for remove.')

    vector = _embed_text(content_snippet)
    qs = Engram.objects.filter(is_active=True)
    for tag in _collection_tags(collection):
        qs = qs.filter(tags__name=tag)

    target = None
    scored = (
        qs.exclude(vector__isnull=True)
        .annotate(distance=CosineDistance('vector', vector))
        .order_by('distance')
    )
    if scored.exists():
        best = scored.first()
        if 1.0 - best.distance >= SIMILARITY_CUTOFF:
            target = best

    if target is None:
        for cand in qs:
            if content_snippet in (cand.description or ''):
                target = cand
                break

    if target is None:
        raise ValueError('No matching entry found to remove.')

    target.is_active = False
    target.save(update_fields=['is_active'])

    return {
        'collection': collection,
        'action': 'remove',
        'entries_count': _count_entries(collection),
        'total_chars': _total_chars(collection),
        'engram_id': str(target.id),
    }
