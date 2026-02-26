"""
Talos Hippocampus
=================

An asynchronous engine for managing permanent memories (Engrams) during reasoning sessions.
"""

import logging
from dataclasses import dataclass

from asgiref.sync import sync_to_async
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.models import Count
from pgvector.django import CosineDistance

from frontal_lobe.models import ModelRegistry, ReasoningSession, ReasoningTurn
from frontal_lobe.synapse import OllamaClient
from hydra.models import HydraHead
from talos_hippocampus.models import TalosEngram, TalosEngramTag

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


class TalosHippocampus(object):
    """
    An asynchronous manager for Talos Engrams. It acts as the permanent storage
    and retrieval mechanism for AI memories. All database I/O is routed through
    this object via `sync_to_async` to preserve event-loop safety.
    """

    @classmethod
    async def get_turn_1_catalog(cls, head: HydraHead, limit: int = 15) -> str:
        """
        Retrieves the indexed catalog of active engrams linked to a specific HydraHead,
        formatted as a context block for the L1 cache.
        """

        def _get_catalog_sync() -> str:
            qs = (
                TalosEngram.objects.filter(
                    heads__node=head.node, is_active=True
                )
                .exclude(heads=head)
                .annotate(
                    session_count=Count('sessions', distinct=True),
                    head_count=Count('heads', distinct=True),
                )
                .order_by('-session_count')
                .prefetch_related('tags')[:limit]
            )

            res_lines = []
            for e in qs:
                tags_str = ', '.join([tag.name for tag in e.tags.all()])
                res_lines.append(
                    f'- ID {e.id} | Sessions: {e.session_count} | Heads: {e.head_count} | Title: {e.name} | Tags: {tags_str}'
                )

            return '\n'.join(res_lines)

        catalog_body = await sync_to_async(_get_catalog_sync)()

        if not catalog_body:
            return (
                '[YOUR CARD CATALOG (ENGRAM INDEX)]\n'
                'Your memory banks are completely empty.\n'
                '(Use mcp_engram_read to read full facts)\n\n'
            )

        return (
            f'[YOUR CARD CATALOG (ENGRAM INDEX)]\n'
            f'[SYSTEM BOOT: RELEVANT ENGRAM INDEX INJECTED]\n'
            f'The following historical memory cards are explicitly linked to this HydraHead:\n\n'
            f'{catalog_body}\n\n'
            f'(Action: The data payloads are currently evicted. Use mcp_engram_read as a Free Action (0 Focus) to retrieve the full facts into your L1 Cache before proceeding.)\n\n'
        )

    @classmethod
    async def get_recent_catalog(cls, session: ReasoningSession) -> str:
        """
        Retrieves a simple list of recently created engrams for normal turns.
        """

        def _get_recent_sync() -> str:
            engrams = session.engram.filter(is_active=True).order_by('created')
            if not engrams.exists():
                return 'Your memory banks are completely empty.'
            return '\n'.join([f'- ID {e.id}: {e.name}' for e in engrams])

        catalog_str = await sync_to_async(_get_recent_sync)()

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
        """Saves a new fact into the Hippocampus as an Engram."""
        registry = await sync_to_async(ModelRegistry.objects.get)(
            id=ModelRegistry.NOMIC_EMBED_TEXT
        )
        client = OllamaClient(registry.name)
        text_payload = f'Title: {title}\nFact: {fact}'
        embedding = await sync_to_async(client.embed)(text_payload)

        def _save_sync() -> 'HippocampusMemoryYield':
            try:
                session = ReasoningSession.objects.get(id=session_id)
                exact_turn = (
                    ReasoningTurn.objects.get(id=turn_id) if turn_id else None
                )
                clean_title = title[:254]

                if embedding:
                    qs = (
                        TalosEngram.objects.exclude(vector__isnull=True)
                        .annotate(distance=CosineDistance('vector', embedding))
                        .order_by('distance')
                    )

                    if qs.exists():
                        best_match = qs.first()
                        similarity = 1.0 - best_match.distance
                        if similarity >= 0.90:
                            msg = (
                                f'Save rejected. High memory overlap detected. You already know this. '
                                f'[0 Focus Awarded]. Here is the existing Engram: {best_match.description}'
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

                existing_engram = TalosEngram.objects.filter(
                    name=clean_title
                ).first()
                if existing_engram:
                    msg = (
                        f"SYSTEM NOTICE: Engram '{clean_title}' already exists in your Hippocampus.\n"
                        f'Current Fact: {existing_engram.description}\n'
                        f'ACTION REQUIRED: If you wish to add new information to this, cast `mcp_engram_update`.'
                    )
                    return HippocampusMemoryYield(
                        intercepted=False, message=msg, similarity=max_sim
                    )

                engram = TalosEngram.objects.create(
                    name=clean_title,
                    description=fact,
                    relevance_score=relevance,
                    vector=embedding if embedding else None,
                )

                engram.sessions.add(session)
                engram.heads.add(session.head)
                if exact_turn:
                    engram.source_turns.add(exact_turn)

                if tags:
                    tag_list = [t.strip() for t in tags.split(',') if t.strip()]
                    for t_name in tag_list:
                        tag_obj, _ = TalosEngramTag.objects.get_or_create(
                            name=t_name
                        )
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

        return await sync_to_async(_save_sync)()

    @classmethod
    async def update_engram(
        cls, session_id: str, title: str, additional_fact: str, turn_id: int
    ) -> 'HippocampusMemoryYield':
        """Appends new findings to an existing Engram."""

        def _get_existing_sync():
            clean_title = title[:254]
            try:
                engram = TalosEngram.objects.get(name=clean_title)
                return engram.description, clean_title
            except TalosEngram.DoesNotExist:
                return None, clean_title

        existing_desc, clean_title = await sync_to_async(_get_existing_sync)()
        if existing_desc is None:
            msg = f"Error: Engram with title '{clean_title}' does not exist. Use `mcp_engram_save` to create it first."
            return HippocampusMemoryYield(
                intercepted=False, message=msg, similarity=0.0
            )

        combined_text = f'{existing_desc}\n\n[UPDATE]: {additional_fact}'
        text_payload = f'Title: {title}\nFact: {combined_text}'

        registry = await sync_to_async(ModelRegistry.objects.get)(
            name='nomic-embed-text'
        )
        client = OllamaClient(registry.name)
        embedding = await sync_to_async(client.embed)(text_payload)

        def _update_sync() -> 'HippocampusMemoryYield':
            try:
                engram = TalosEngram.objects.get(name=clean_title)
                session = ReasoningSession.objects.get(id=session_id)
                exact_turn = (
                    ReasoningTurn.objects.get(id=turn_id) if turn_id else None
                )

                if embedding:
                    qs = (
                        TalosEngram.objects.exclude(id=engram.id)
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
                engram.save(update_fields=['description', 'vector'])

                engram.sessions.add(session)
                if exact_turn:
                    engram.source_turns.add(exact_turn)

                msg = f"Success: Engram '{engram.name}' has been updated with the new data."
                return HippocampusMemoryYield(
                    intercepted=False, message=msg, similarity=max_sim
                )
            except Exception as e:
                logger.error(f"Failed to update engram '{title}': {e}")
                return HippocampusMemoryYield(
                    intercepted=False,
                    message=f'Update Error: {str(e)}',
                    similarity=0.0,
                )

        return await sync_to_async(_update_sync)()

    @classmethod
    async def read_engram(cls, session_id: str, engram_id: int) -> str:
        """Reads the full fact of a specific Engram by ID."""

        def _read_sync() -> str:
            try:
                engram = TalosEngram.objects.get(id=engram_id, is_active=True)
                session = ReasoningSession.objects.get(id=session_id)

                engram.sessions.add(session)

                tags = ', '.join([t.name for t in engram.tags.all()])
                return f'--- ENGRAM {engram.id}: {engram.name} ---\nTags: {tags}\nFact: {engram.description}'
            except TalosEngram.DoesNotExist:
                return f'Error: Engram ID {engram_id} not found in Hippocampus.'
            except Exception as e:
                logger.error(f'Failed to read engram {engram_id}: {e}')
                return f'Error: {str(e)}'

        return await sync_to_async(_read_sync)()

    @classmethod
    async def search_engrams(
        cls, query: str = '', tags: str = '', limit: int = 10
    ) -> str:
        """Searches the permanent Hippocampus catalog."""

        def _search_sync() -> str:
            qs = TalosEngram.objects.filter(is_active=True)

            if query:
                qs = qs.annotate(
                    search=SearchVector('name', 'description')
                ).filter(search=SearchQuery(query))
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

        return await sync_to_async(_search_sync)()
