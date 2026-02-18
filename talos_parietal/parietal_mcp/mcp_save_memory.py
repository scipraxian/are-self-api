import hashlib

from asgiref.sync import sync_to_async
from django.db import transaction

from talos_hippocampus.models import TalosEngram, TalosEngramTag
from talos_reasoning.models import ReasoningSession


@sync_to_async
def _save_sync(
    session_id: str,
    fact: str,
    tags: str = '',
    relevance: float = 1.0,
    update_id: int = None,
) -> str:

    try:
        session = ReasoningSession.objects.get(id=session_id)
        latest_turn = session.turns.last()

        engram = None
        created = False

        with transaction.atomic():
            # A. UPDATE Existing Memory
            if update_id:
                try:
                    engram = TalosEngram.objects.get(id=update_id)
                    engram.description = fact  # Update the content
                    engram.relevance_score = relevance
                    engram.save()
                    action = 'Updated'
                except TalosEngram.DoesNotExist:
                    return f'Error: Memory ID {update_id} not found.'

            # B. CREATE New Memory
            else:
                # Generate a unique name/hash to prevent duplicates
                fact_hash = hashlib.sha256(
                    fact.strip().lower().encode('utf-8')
                ).hexdigest()[:64]
                engram, created = TalosEngram.objects.get_or_create(
                    name=fact_hash,
                    defaults={
                        'description': fact,
                        'relevance_score': relevance,
                    },
                )
                action = 'Created' if created else 'Linked to existing'

            # Common: Link Session & Tags
            engram.sessions.add(session)
            if latest_turn:
                engram.source_turns.add(latest_turn)

            if tags:
                tag_list = [t.strip() for t in tags.split(',') if t.strip()]
                for t_name in tag_list:
                    tag_obj, _ = TalosEngramTag.objects.get_or_create(
                        name=t_name
                    )
                    engram.tags.add(tag_obj)

        return f'Success: {action} Memory {engram.id}.'

    except Exception as e:
        return f'Memory Error: {str(e)}'


async def mcp_save_memory(
    session_id: str,
    fact: str,
    tags: str = '',
    relevance: float = 1.0,
    update_id: int = None,
) -> str:
    """
    MCP Tool: Saves a fact. Can create new or update existing if 'update_id' is provided.
    Always links the memory to the current session.
    """
    return await _save_sync(session_id, fact, tags, relevance, update_id)
