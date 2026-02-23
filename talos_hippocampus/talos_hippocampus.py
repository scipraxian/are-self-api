"""
Talos Hippocampus
=================

An asynchronous engine for managing permanent memories (Engrams) during reasoning sessions.
"""

import logging

from asgiref.sync import sync_to_async
from django.db.models import Count, Q

from hydra.models import HydraHead
from talos_hippocampus.models import TalosEngram, TalosEngramTag
from frontal_lobe.models import ReasoningSession

logger = logging.getLogger(__name__)


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
            qs = (TalosEngram.objects.filter(
                heads__spell=head.spell, is_active=True).annotate(
                    session_count=Count('sessions', distinct=True),
                    head_count=Count('heads', distinct=True),
                ).order_by('-session_count').prefetch_related('tags')[:limit])

            res_lines = []
            for e in qs:
                tags_str = ', '.join([tag.name for tag in e.tags.all()])
                res_lines.append(
                    f'- ID {e.id} | Sessions: {e.session_count} | Heads: {e.head_count} | Title: {e.name} | Tags: {tags_str}'
                )

            return '\n'.join(res_lines)

        catalog_body = await sync_to_async(_get_catalog_sync)()

        if not catalog_body:
            return (f'[YOUR CARD CATALOG (ENGRAM INDEX)]\n'
                    f'Your memory banks are completely empty.\n'
                    f'(Use mcp_engram_read to read full facts)\n\n')

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

        return (f'[YOUR CARD CATALOG (ENGRAM INDEX)]\n'
                f'{catalog_str}\n'
                f'(Use mcp_engram_read to read full facts)\n\n')

    @classmethod
    async def save_engram(
        cls,
        session_id: str,
        title: str,
        fact: str,
        tags: str = '',
        relevance: float = 1.0,
    ) -> str:
        """Saves a new fact into the Hippocampus as an Engram."""

        def _save_sync() -> str:
            try:
                session = ReasoningSession.objects.get(id=session_id)
                latest_turn = session.turns.last()
                clean_title = title[:254]

                existing_engram = TalosEngram.objects.filter(
                    name=clean_title).first()
                if existing_engram:
                    return (
                        f"SYSTEM NOTICE: Engram '{clean_title}' already exists in your Hippocampus.\n"
                        f'Current Fact: {existing_engram.description}\n'
                        f'ACTION REQUIRED: If you wish to add new information to this, cast `mcp_engram_update`.'
                    )

                engram = TalosEngram.objects.create(
                    name=clean_title,
                    description=fact,
                    relevance_score=relevance,
                )

                engram.sessions.add(session)
                if latest_turn:
                    engram.source_turns.add(latest_turn)

                if tags:
                    tag_list = [t.strip() for t in tags.split(',') if t.strip()]
                    for t_name in tag_list:
                        tag_obj, _ = TalosEngramTag.objects.get_or_create(
                            name=t_name)
                        engram.tags.add(tag_obj)

                return f'Success: Memory Card [{engram.id}: {engram.name}] permanently crystallized.'
            except Exception as e:
                logger.error(f"Failed to save engram '{title}': {e}")
                return f'Memory Error: {str(e)}'

        return await sync_to_async(_save_sync)()

    @classmethod
    async def update_engram(cls, session_id: str, title: str,
                            additional_fact: str) -> str:
        """Appends new findings to an existing Engram."""

        def _update_sync() -> str:
            try:
                clean_title = title[:254]
                engram, _ = TalosEngram.objects.get_or_create(name=clean_title)
                session = ReasoningSession.objects.get(id=session_id)
                latest_turn = session.turns.last()

                engram.description = (
                    f'{engram.description}\n\n[UPDATE]: {additional_fact}')
                engram.save(update_fields=['description'])

                engram.sessions.add(session)
                if latest_turn:
                    engram.source_turns.add(latest_turn)

                return f"Success: Engram '{engram.name}' has been updated with the new data."
            except TalosEngram.DoesNotExist:
                return f"Error: Engram with title '{clean_title}' does not exist. Use `mcp_engram_save` to create it first."
            except Exception as e:
                logger.error(f"Failed to update engram '{title}': {e}")
                return f'Update Error: {str(e)}'

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
    async def search_engrams(cls,
                             query: str = '',
                             tags: str = '',
                             limit: int = 10) -> str:
        """Searches the permanent Hippocampus catalog."""

        def _search_sync() -> str:
            qs = TalosEngram.objects.filter(is_active=True)

            if query:
                qs = qs.filter(
                    Q(description__icontains=query) | Q(name__icontains=query))
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
