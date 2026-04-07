"""
Hippocampus
===========

An asynchronous engine for managing permanent memories (Engrams) during reasoning sessions.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from asgiref.sync import sync_to_async
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.models import Count
from pgvector.django import CosineDistance

from central_nervous_system.models import Spike
from frontal_lobe.models import NOMIC_EMBED_TEXT_MODEL, ReasoningSession, ReasoningTurn
from frontal_lobe.synapse import OllamaClient
from hippocampus.models import Engram, EngramTag

logger = logging.getLogger(__name__)


@dataclass
class HippocampusMemoryYield:
    """A strictly typed yield for the Parietal Lobe to consume."""

    message: str
    intercepted: bool
    similarity: float

    @property
    def focus_yield(self) -> int:
        if self.intercepted:
            return 0
        novelty = max(0.0, 1.0 - self.similarity)
        return max(1, int(10 * novelty))

    @property
    def xp_yield(self) -> int:
        if self.intercepted:
            return 0
        novelty = max(0.0, 1.0 - self.similarity)
        return max(5, int(100 * novelty))

    def __str__(self):
        return self.message


# ---------------------------------------------------------------------------
# Pure Synchronous DB Operations (Module Level, Flat, Fully Scoped)
# ---------------------------------------------------------------------------


def _get_recent_sync(session: ReasoningSession) -> str:
    engrams = session.engrams.filter(is_active=True).order_by('created')
    if not engrams.exists():
        return 'You have no Engrams in your Hippocampus yet.'
    return '\n'.join([f'- ID {e.id}: {e.name}' for e in engrams])


def _get_catalog_sync(spike: Spike, limit: int) -> str:
    qs = (
        Engram.objects.filter(spikes__neuron=spike.neuron, is_active=True)
        .exclude(spikes=spike)
        .annotate(
            session_count=Count('sessions', distinct=True),
            head_count=Count('spikes', distinct=True),
        )
        .order_by('-modified')
        .prefetch_related('tags', 'sessions', 'spikes')[:limit]
    )

    res_lines = []
    for engram in qs:
        tags_str = ', '.join([tag.name for tag in engram.tags.all()])
        res_lines.append(
            f'- ID {engram.id} | '
            f'Sessions: {engram.sessions.count()} | '
            f'Spikes: {engram.spikes.count()} | '
            f'Title: {engram.name} | '
            f'Tags: {tags_str}'
        )

    return '\n'.join(res_lines)


def _read_sync(engram_id: str, session_id: str) -> str:
    try:
        engram = Engram.objects.get(id=engram_id, is_active=True)
        session = ReasoningSession.objects.get(id=session_id)
        identity_disc = session.identity_disc

        engram.sessions.add(session)
        if session.spike:
            engram.spikes.add(session.spike)
        if identity_disc:
            if engram.creator_id is None:
                engram.creator = identity_disc
                engram.save(update_fields=['creator'])
            engram.identity_discs.add(identity_disc)
            identity_disc.memories.add(engram)

        tags = ', '.join([t.name for t in engram.tags.all()])
        return f'--- ENGRAM {engram.id}: {engram.name} ---\nTags: {tags}\nFact: {engram.description}'
    except Engram.DoesNotExist:
        return f'Error: Engram ID {engram_id} not found in Hippocampus.'
    except Exception as e:
        logger.error(f'Failed to read engram {engram_id}: {e}')
        return f'Error: {str(e)}'


def _search_sync(query: str, tags: str, limit: int) -> str:
    qs = Engram.objects.filter(is_active=True)

    if query:
        qs = qs.annotate(search=SearchVector('name', 'description')).filter(
            search=SearchQuery(query)
        )
    if tags:
        tag_list = [t.strip() for t in tags.split(',') if t.strip()]
        qs = qs.filter(tags__name__in=tag_list)

    qs = qs.distinct().order_by('-relevance_score', '-created')[:limit]

    if not qs.exists():
        return 'No engrams found matching criteria.'

    results = [
        'Found Engrams in Hippocampus (Use mcp_engram_read to read the full fact):'
    ]
    for m in qs:
        tag_str = ', '.join([t.name for t in m.tags.all()])
        results.append(
            f'ID {m.id} | Title: {m.name} | Tags: [{tag_str}] | Rel: {m.relevance_score}'
        )

    return '\n'.join(results)


def _save_sync(
    session_id: str,
    title: str,
    fact: str,
    turn_id: int,
    tags: str,
    relevance: float,
    embedding: Optional[list],
) -> HippocampusMemoryYield:
    """Strictly for creating new engrams. Uses safe filters for name collisions."""
    try:
        session = ReasoningSession.objects.get(id=session_id)
        exact_turn = ReasoningTurn.objects.get(id=turn_id) if turn_id else None
        clean_title = title[:254]
        identity_disc = session.identity_disc

        if embedding:
            qs = (
                Engram.objects.exclude(vector__isnull=True)
                .annotate(distance=CosineDistance('vector', embedding))
                .order_by('distance')
            )

            if qs.exists():
                best_match = qs.first()
                similarity = 1.0 - best_match.distance
                if similarity >= 0.90:
                    msg = (
                        f'Save rejected. High memory overlap detected. You already know this. '
                        f'[0 Focus Awarded]. Here is the existing Engram (ID: {best_match.id}): {best_match.description}'
                    )
                    return HippocampusMemoryYield(
                        intercepted=True,
                        message=msg,
                        similarity=similarity,
                    )
                max_sim = similarity
            else:
                max_sim = 0.0
        else:
            max_sim = 0.0

        # Safe collision check without crashing on MultipleObjectsReturned
        existing_engram = Engram.objects.filter(name=clean_title).first()
        if existing_engram:
            msg = (
                f"SYSTEM NOTICE: Engram with title '{clean_title}' already exists (ID: {existing_engram.id}).\n"
                f'Current Fact: {existing_engram.description}\n'
                f'ACTION REQUIRED: Use `mcp_engram_update` with ID {existing_engram.id} to append new information.'
            )
            return HippocampusMemoryYield(
                intercepted=False, message=msg, similarity=max_sim
            )

        engram = Engram.objects.create(
            name=clean_title,
            description=fact,
            relevance_score=relevance,
            vector=embedding if embedding else None,
        )

        engram.sessions.add(session)
        if session.spike:
            engram.spikes.add(session.spike)
        if exact_turn:
            engram.source_turns.add(exact_turn)

        if identity_disc:
            if engram.creator_id is None:
                engram.creator = identity_disc
                engram.save(update_fields=['creator'])
            engram.identity_discs.add(identity_disc)
            identity_disc.memories.add(engram)

        if tags:
            tag_list = [t.strip() for t in tags.split(',') if t.strip()]
            for t_name in tag_list:
                tag_obj, _ = EngramTag.objects.get_or_create(name=t_name)
                engram.tags.add(tag_obj)

        msg = f'Success: Memory Card [{engram.id}: {engram.name}] permanently crystallized.'
        return HippocampusMemoryYield(
            intercepted=False, message=msg, similarity=max_sim
        )
    except Exception as e:
        logger.error(f"Failed to save engram '{title}': {e}")
        return HippocampusMemoryYield(
            intercepted=False,
            message=f'Memory Error: {str(e)}',
            similarity=0.0,
        )


def _get_existing_desc_sync(
    engram_id: str,
) -> tuple[Optional[str], Optional[str]]:
    """Strictly lookup by UUID for updates."""
    try:
        engram = Engram.objects.get(id=engram_id)
        return engram.description, engram.name
    except Engram.DoesNotExist:
        return None, None


def _update_sync(
    session_id: str,
    engram_id: str,
    combined_text: str,
    turn_id: int,
    embedding: Optional[list],
) -> HippocampusMemoryYield:
    """Strictly updates by UUID."""
    try:
        engram = Engram.objects.get(id=engram_id)

        session = ReasoningSession.objects.get(id=session_id)
        exact_turn = ReasoningTurn.objects.get(id=turn_id) if turn_id else None
        identity_disc = session.identity_disc

        if embedding:
            qs = (
                Engram.objects.exclude(id=engram.id)
                .exclude(vector__isnull=True)
                .annotate(distance=CosineDistance('vector', embedding))
                .order_by('distance')
            )
            if qs.exists():
                best_match = qs.first()
                max_sim = 1.0 - best_match.distance
            else:
                max_sim = 0.0
        else:
            max_sim = 0.0

        engram.description = combined_text
        if embedding:
            engram.vector = embedding

        update_fields = ['description', 'vector']
        if identity_disc and engram.creator_id is None:
            engram.creator = identity_disc
            update_fields.append('creator')

        engram.save(update_fields=update_fields)

        engram.sessions.add(session)
        if session.spike:
            engram.spikes.add(session.spike)
        if exact_turn:
            engram.source_turns.add(exact_turn)
        if identity_disc:
            engram.identity_discs.add(identity_disc)
            identity_disc.memories.add(engram)

        msg = f"Success: Engram '{engram.name}' (ID: {engram.id}) has been updated with the new data."
        return HippocampusMemoryYield(
            intercepted=False, message=msg, similarity=max_sim
        )
    except Exception as e:
        logger.error(f"Failed to update engram '{engram_id}': {e}")
        return HippocampusMemoryYield(
            intercepted=False,
            message=f'Update Error: {str(e)}',
            similarity=0.0,
        )


# ---------------------------------------------------------------------------
# The Interface
# ---------------------------------------------------------------------------


class Hippocampus(object):
    """An asynchronous manager for Engrams."""

    @classmethod
    def get_turn_1_catalog(cls, spike: Spike, limit: int = 15) -> str:
        catalog_body = _get_catalog_sync(spike, limit)
        if not catalog_body:
            return (
                '[YOUR CARD CATALOG (ENGRAM INDEX)]\n'
                'Your memory cache is empty.\n'
                '(Use mcp_engram_search to find others)\n\n'
            )

        return (
            f'[YOUR CARD CATALOG (ENGRAM INDEX)]\n'
            f'[SYSTEM BOOT: RELEVANT ENGRAM INDEX INJECTED]\n'
            f'The following historical memory cards are explicitly linked to this Spike:\n\n'
            f'{catalog_body}\n\n'
            f'(Action: The data payloads are currently evicted. Use mcp_engram_read as a Free Action (0 Focus) to retrieve the full facts into your L1 Cache before proceeding.)\n\n'
        )

    @classmethod
    def get_recent_catalog(cls, session: ReasoningSession) -> str:
        catalog_str = _get_recent_sync(session)
        return (
            f'[YOUR CARD CATALOG (ENGRAM INDEX)]\n'
            f'{catalog_str}\n'
            f'(Use mcp_engram_read to read full facts)\n\n'
        )

    @classmethod
    async def save_engram(
        cls,
        session_id: str,
        title: str,
        fact: str,
        turn_id: int,
        tags: str = '',
        relevance: float = 1.0,
    ) -> 'HippocampusMemoryYield':
        """Acts as CREATE. Notes its action in docstring."""
        client = OllamaClient(NOMIC_EMBED_TEXT_MODEL)
        text_payload = f'Title: {title}\nFact: {fact}'
        embedding = await sync_to_async(client.embed)(text_payload)

        return await sync_to_async(_save_sync)(
            session_id, title, fact, turn_id, tags, relevance, embedding
        )

    @classmethod
    async def update_engram(
        cls, session_id: str, engram_id: str, additional_fact: str, turn_id: int
    ) -> 'HippocampusMemoryYield':
        """Acts as UPDATE. Strictly uses UUID/ID."""
        existing_desc, engram_title = await sync_to_async(
            _get_existing_desc_sync
        )(engram_id)

        if existing_desc is None:
            msg = f"Error: Engram ID '{engram_id}' does not exist. Use `mcp_engram_save` to create it."
            return HippocampusMemoryYield(
                intercepted=False, message=msg, similarity=0.0
            )

        combined_text = f'{existing_desc}\n\n[UPDATE]: {additional_fact}'
        text_payload = f'Title: {engram_title}\nFact: {combined_text}'

        client = OllamaClient(NOMIC_EMBED_TEXT_MODEL)
        embedding = await sync_to_async(client.embed)(text_payload)

        return await sync_to_async(_update_sync)(
            session_id, engram_id, combined_text, turn_id, embedding
        )

    @classmethod
    async def read_engram(cls, session_id: str, engram_id: str) -> str:
        return await sync_to_async(_read_sync)(engram_id, session_id)

    @classmethod
    async def search_engrams(
        cls, query: str = '', tags: str = '', limit: int = 10
    ) -> str:
        return await sync_to_async(_search_sync)(query, tags, limit)
