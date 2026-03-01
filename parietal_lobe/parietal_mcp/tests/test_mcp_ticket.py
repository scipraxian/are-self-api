import asyncio

import pytest
from asgiref.sync import sync_to_async

from parietal_lobe.parietal_mcp.gateway import ParietalMCP
from prefrontal_cortex.models import (
    PFCComment,
    PFCEpic,
    PFCItemStatus,
    PFCStory,
    PFCTask,
)


@pytest.fixture
def pfc_setup():
    """Seeds the test database with required Agile statuses."""
    backlog, _ = PFCItemStatus.objects.get_or_create(
        id=1, defaults={'name': 'Backlog'}
    )
    in_progress, _ = PFCItemStatus.objects.get_or_create(
        id=3, defaults={'name': 'In Progress'}
    )
    return {'backlog': backlog, 'in_progress': in_progress}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_ticket_create_hierarchy(pfc_setup):
    """Verifies the AI can create a full Epic -> Story -> Task chain."""

    # 1. Create Epic
    epic_res = await ParietalMCP.execute(
        'mcp_ticket',
        {
            'action': 'CREATE',
            'item_type': 'EPIC',
            'name': 'Multiplayer Overhaul',
            'description': 'Fix the sync issues.',
        },
    )
    assert 'Success: Created EPIC' in epic_res

    # Extract UUID (e.g., "Success: Created EPIC '...' with ID: 1234-...")
    epic_id = epic_res.split('ID: ')[1].strip()

    # 2. Create Story (With DoR Fields)
    story_res = await ParietalMCP.execute(
        'mcp_ticket',
        {
            'action': 'CREATE',
            'item_type': 'STORY',
            'parent_id': epic_id,
            'name': 'Sync Player Transform',
            'perspective': 'As a client...',
            'assertions': 'Assert X, Y, Z match.',
        },
    )
    assert 'Success: Created STORY' in story_res
    story_id = story_res.split('ID: ')[1].strip()

    # 3. Create Task
    task_res = await ParietalMCP.execute(
        'mcp_ticket',
        {
            'action': 'CREATE',
            'item_type': 'TASK',
            'parent_id': story_id,
            'name': 'Write RPCs',
            'status': 'In Progress',
        },
    )
    assert 'Success: Created TASK' in task_res
    task_id = task_res.split('ID: ')[1].strip()

    # --- VERIFY DATABASE INTEGRITY ---
    epic = await sync_to_async(PFCEpic.objects.get)(id=epic_id)
    assert epic.name == 'Multiplayer Overhaul'
    assert epic.status.name == 'Backlog'

    story = await sync_to_async(PFCStory.objects.get)(id=story_id)
    assert str(story.epic_id) == epic_id
    assert story.assertions == 'Assert X, Y, Z match.'

    task = await sync_to_async(PFCTask.objects.get)(id=task_id)
    assert str(task.story_id) == story_id
    assert task.status.name == 'In Progress'


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_ticket_read_and_comment(pfc_setup):
    """Verifies the AI can leave comments and read the full context window of a ticket."""
    epic = await sync_to_async(PFCEpic.objects.create)(
        name='Context Epic',
        description='Testing comments',
        status=pfc_setup['backlog'],
    )
    epic_id = str(epic.id)

    # Add Comment via MCP
    comment_res = await ParietalMCP.execute(
        'mcp_ticket',
        {
            'action': 'COMMENT',
            'item_type': 'EPIC',
            'item_id': epic_id,
            'text': 'This is a neural analysis comment.',
        },
    )
    assert 'Success: Added comment' in comment_res

    # Read via MCP
    read_res = await ParietalMCP.execute(
        'mcp_ticket',
        {
            'action': 'READ',
            'item_type': 'EPIC',
            'item_id': epic_id,
        },
    )

    # Assertions
    assert '--- EPIC: Context Epic [Backlog] ---' in read_res
    assert 'Description:\nTesting comments' in read_res
    assert 'This is a neural analysis comment.' in read_res


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_ticket_update(pfc_setup):
    """Verifies the AI can mutate existing tickets."""
    # Create a dummy task
    epic = await sync_to_async(PFCEpic.objects.create)(name='Dummy Epic')
    story = await sync_to_async(PFCStory.objects.create)(
        name='Dummy Story', epic=epic
    )
    task = await sync_to_async(PFCTask.objects.create)(
        name='Old Task', status=pfc_setup['backlog'], story=story
    )
    task_id = str(task.id)

    update_res = await ParietalMCP.execute(
        'mcp_ticket',
        {
            'action': 'UPDATE',
            'item_type': 'TASK',
            'item_id': task_id,
            'name': 'New Task Name',
            'status': 'In Progress',
        },
    )
    assert 'Success: Updated TASK' in update_res

    # Verify DB
    await sync_to_async(task.refresh_from_db)()
    assert task.name == 'New Task Name'
    assert task.status.name == 'In Progress'


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mcp_ticket_error_handling(pfc_setup):
    """Verifies edge cases and invalid parameters are caught gracefully."""

    # 1. Invalid Action
    res1 = await ParietalMCP.execute(
        'mcp_ticket', {'action': 'DESTROY', 'item_type': 'EPIC'}
    )
    assert 'Error: Invalid action' in res1

    # 2. Create Story without Parent
    res2 = await ParietalMCP.execute(
        'mcp_ticket',
        {'action': 'CREATE', 'item_type': 'STORY', 'name': 'Orphan Story'},
    )
    assert "Error: 'parent_id' (Epic UUID) is required" in res2

    # 3. Read missing item
    res3 = await ParietalMCP.execute(
        'mcp_ticket',
        {
            'action': 'READ',
            'item_type': 'TASK',
            'item_id': '00000000-0000-0000-0000-000000000000',
        },
    )
    assert 'Error: Referenced object not found.' in res3
