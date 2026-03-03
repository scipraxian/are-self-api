import pytest
from asgiref.sync import sync_to_async
from django.test import TransactionTestCase

from central_nervous_system.models import Spike, SpikeTrain
from frontal_lobe.models import ReasoningSession, ReasoningStatusID
from parietal_lobe.parietal_mcp.gateway import ParietalMCP
from parietal_lobe.parietal_mcp.mcp_ticket import TicketConstants
from prefrontal_cortex.models import (
    PFCEpic,
    PFCStory,
    PFCTask,
)


class MCPTicketTest(TransactionTestCase):
    """
    Integration tests for the Agile Board MCP Tool.
    Utilizes the canonical production fixtures to ensure status mappings and constraints are accurate.
    """

    fixtures = [
        'environments/fixtures/initial_data.json',
        'peripheral_nervous_system/fixtures/initial_data.json',
        'peripheral_nervous_system/fixtures/test_agents.json',
        'central_nervous_system/fixtures/initial_data.json',
        'frontal_lobe/fixtures/initial_data.json',
        'parietal_lobe/fixtures/initial_data.json',
        'prefrontal_cortex/fixtures/initial_data.json',
    ]

    def setUp(self):
        """Synchronous DB setup that runs before each async test method."""
        self.spike_train = SpikeTrain.objects.create(status_id=1)

        self.spike = Spike.objects.create(
            spike_train=self.spike_train,
            status_id=1,
            blackboard={'persona': 'ORACLE'},
        )

        self.session = ReasoningSession.objects.create(
            spike=self.spike, status_id=ReasoningStatusID.ACTIVE
        )
        self.session_id = str(self.session.id)

    @pytest.mark.asyncio
    async def test_validation_rule_1_pao_enforcer(self):
        """Rule 1: Rejects Story creation/updates missing Perspective, Assertions, or Outside."""
        res1 = await ParietalMCP.execute(
            'mcp_ticket',
            {
                'action': 'CREATE',
                'item_type': 'STORY',
                'parent_id': '00000000-0000-0000-0000-000000000000',
                'name': 'Lazy Story',
            },
        )
        self.assertIn(TicketConstants.ERR_PAO, res1)

        res2 = await ParietalMCP.execute(
            'mcp_ticket',
            {
                'action': 'CREATE',
                'item_type': 'STORY',
                'parent_id': '00000000-0000-0000-0000-000000000000',
                'name': 'Almost Story',
                'perspective': 'As a user...',
                'assertions': 'Assert True',
            },
        )
        self.assertIn(TicketConstants.ERR_PAO, res2)

    @pytest.mark.asyncio
    async def test_validation_rule_2_dor_gatekeeper(self):
        """Rule 2: Rejects Status promotion to SELECTED without Dependencies/Demo Specs."""
        epic = await sync_to_async(PFCEpic.objects.create)(
            name='Epic 1', status_id=1
        )

        story_res = await ParietalMCP.execute(
            'mcp_ticket',
            {
                'action': 'CREATE',
                'item_type': 'STORY',
                'parent_id': str(epic.id),
                'name': 'Valid Story',
                'perspective': 'P',
                'assertions': 'A',
                'outside': 'O',
            },
        )
        story_id = story_res.split('ID: ')[1].strip()

        update_res = await ParietalMCP.execute(
            'mcp_ticket',
            {
                'action': 'UPDATE',
                'item_type': 'STORY',
                'item_id': story_id,
                'status': 'SELECTED_FOR_DEVELOPMENT',
            },
        )
        self.assertIn(TicketConstants.ERR_DOR_DEMO, update_res)

    @pytest.mark.asyncio
    async def test_validation_rule_3_complexity_shield(self):
        """Rule 3: Prevents the Oracle PM from assigning complexity points."""
        epic = await sync_to_async(PFCEpic.objects.create)(
            name='Epic 1', status_id=1
        )

        res = await ParietalMCP.execute(
            'mcp_ticket',
            {
                'action': 'CREATE',
                'item_type': 'STORY',
                'parent_id': str(epic.id),
                'name': 'Bidding Story',
                'perspective': 'P',
                'assertions': 'A',
                'outside': 'O',
                'complexity': 5,
                'session_id': self.session_id,
            },
        )
        self.assertIn(TicketConstants.ERR_COMPLEXITY, res)

    @pytest.mark.asyncio
    async def test_validation_rule_4_breadcrumb_reward(self):
        """Rule 4: Grants silent +XP and +Focus for commenting."""
        epic = await sync_to_async(PFCEpic.objects.create)(
            name='Epic 1', status_id=1
        )

        from parietal_lobe.parietal_mcp.mcp_ticket import mcp_ticket

        yield_obj = await mcp_ticket(
            action='COMMENT',
            item_type='EPIC',
            item_id=str(epic.id),
            text='A highly analytical thought.',
        )

        self.assertIn('Success: Added comment', yield_obj.message)
        self.assertEqual(yield_obj.focus_yield, 3)
        self.assertEqual(yield_obj.xp_yield, 15)

    @pytest.mark.asyncio
    async def test_mcp_ticket_create_hierarchy(self):
        """Verifies the AI can create a full Epic -> Story -> Task chain."""
        epic_res = await ParietalMCP.execute(
            'mcp_ticket',
            {
                'action': 'CREATE',
                'item_type': 'EPIC',
                'name': 'Multiplayer Overhaul',
                'description': 'Fix the sync issues.',
            },
        )
        self.assertIn('Success: Created EPIC', epic_res)
        epic_id = epic_res.split('ID: ')[1].strip()

        story_res = await ParietalMCP.execute(
            'mcp_ticket',
            {
                'action': 'CREATE',
                'item_type': 'STORY',
                'parent_id': epic_id,
                'name': 'Sync Player Transform',
                'perspective': 'As a client...',
                'assertions': 'Assert X, Y, Z match.',
                'outside': 'Must not break Z.',
            },
        )
        self.assertIn('Success: Created STORY', story_res)
        story_id = story_res.split('ID: ')[1].strip()

        task_res = await ParietalMCP.execute(
            'mcp_ticket',
            {
                'action': 'CREATE',
                'item_type': 'TASK',
                'parent_id': story_id,
                'name': 'Write RPCs',
                'status': 'IN_PROGRESS',
            },
        )
        self.assertIn('Success: Created TASK', task_res)
        task_id = task_res.split('ID: ')[1].strip()

        # FIX: Explicitly eager-load the status relations using select_related
        epic = await sync_to_async(
            PFCEpic.objects.select_related('status').get
        )(id=epic_id)
        self.assertEqual(epic.name, 'Multiplayer Overhaul')
        self.assertEqual(epic.status.name, 'Backlog')

        story = await sync_to_async(
            PFCStory.objects.select_related('status').get
        )(id=story_id)
        self.assertEqual(str(story.epic_id), epic_id)
        self.assertEqual(story.assertions, 'Assert X, Y, Z match.')

        task = await sync_to_async(
            PFCTask.objects.select_related('status').get
        )(id=task_id)
        self.assertEqual(str(task.story_id), story_id)
        self.assertEqual(task.status.name, 'In Progress')

    @pytest.mark.asyncio
    async def test_mcp_ticket_read_and_comment(self):
        """Verifies the AI can leave comments and read the full context window of a ticket."""
        epic = await sync_to_async(PFCEpic.objects.create)(
            name='Context Epic',
            description='Testing comments',
            status_id=1,
        )
        epic_id = str(epic.id)

        comment_res = await ParietalMCP.execute(
            'mcp_ticket',
            {
                'action': 'COMMENT',
                'item_type': 'EPIC',
                'item_id': epic_id,
                'text': 'This is a neural analysis comment.',
            },
        )
        self.assertIn('Success: Added comment', comment_res)

        read_res = await ParietalMCP.execute(
            'mcp_ticket',
            {
                'action': 'READ',
                'item_type': 'EPIC',
                'item_id': epic_id,
            },
        )

        self.assertIn('--- EPIC: Context Epic [Backlog] ---', read_res)
        self.assertIn('Description:\nTesting comments', read_res)
        self.assertIn('This is a neural analysis comment.', read_res)

    @pytest.mark.asyncio
    async def test_mcp_ticket_update(self):
        """Verifies the AI can mutate existing tickets."""
        epic = await sync_to_async(PFCEpic.objects.create)(
            name='Dummy Epic', status_id=1
        )
        story = await sync_to_async(PFCStory.objects.create)(
            name='Dummy Story', epic=epic, status_id=1
        )
        task = await sync_to_async(PFCTask.objects.create)(
            name='Old Task', status_id=1, story=story
        )
        task_id = str(task.id)

        update_res = await ParietalMCP.execute(
            'mcp_ticket',
            {
                'action': 'UPDATE',
                'item_type': 'TASK',
                'item_id': task_id,
                'name': 'New Task Name',
                'status': 'IN_PROGRESS',
            },
        )
        self.assertIn('Success: Updated TASK', update_res)

        # FIX: Re-fetch with select_related instead of calling refresh_from_db()
        fresh_task = await sync_to_async(
            PFCTask.objects.select_related('status').get
        )(id=task_id)
        self.assertEqual(fresh_task.name, 'New Task Name')
        self.assertEqual(fresh_task.status.name, 'In Progress')

    @pytest.mark.asyncio
    async def test_mcp_ticket_error_handling(self):
        """Verifies edge cases and invalid parameters are caught gracefully."""
        res1 = await ParietalMCP.execute(
            'mcp_ticket', {'action': 'DESTROY', 'item_type': 'EPIC'}
        )
        self.assertIn('Error: Invalid action', res1)

        # FIX: Provide dummy PAO fields so the bouncer lets it through to the missing parent check
        res2 = await ParietalMCP.execute(
            'mcp_ticket',
            {
                'action': 'CREATE',
                'item_type': 'STORY',
                'name': 'Orphan Story',
                'perspective': 'P',
                'assertions': 'A',
                'outside': 'O',
            },
        )
        self.assertIn("Error: 'parent_id' (Epic UUID) is required", res2)

        res3 = await ParietalMCP.execute(
            'mcp_ticket',
            {
                'action': 'READ',
                'item_type': 'TASK',
                'item_id': '00000000-0000-0000-0000-000000000000',
            },
        )
        self.assertIn('Error: Referenced object not found.', res3)
