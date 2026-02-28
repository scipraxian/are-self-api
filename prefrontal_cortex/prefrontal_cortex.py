import logging
from typing import Tuple

from asgiref.sync import sync_to_async
from pgvector.django import CosineDistance

from frontal_lobe.frontal_lobe import FrontalLobe
from frontal_lobe.models import ModelRegistry
from frontal_lobe.synapse import OllamaClient
from central_nervous_system.models import HydraHead
from prefrontal_cortex.models import PFCItemStatus, PFCStory, PFCTask

logger = logging.getLogger(__name__)


class PrefrontalCortex:
    """
    The Strategic Router.
    Maps upstream workflow provenance to the Agile Board to determine
    if Talos should be dispatched to work on a specific Story.
    """

    # 0.0 is an exact match, 1.0 is completely orthogonal.
    # A distance of 0.2 means 80% similarity.
    MAX_ALLOWED_DISTANCE = 0.25

    def __init__(self, head_id: str):
        self.head_id = head_id
        self.head = None
        self.provenance = None
        self.environment = None

    async def engage(self) -> Tuple[int, str]:
        logger.info(f'[PFC] Routing evaluation started for Head {self.head_id}')

        await self._load_context()

        if not self.provenance:
            return 200, '[PFC] No provenance found. Skipping routing.'

        # 1. Define the Meta-Context (What just happened?)
        # We don't read the logs. We read the graph's intent.
        routing_context = self._build_routing_context()

        # 2. Vectorize the Meta-Context
        embedding = await self._generate_vector(routing_context)
        if not embedding:
            return 500, '[PFC] Failed to generate routing vector from Synapse.'

        # 3. Consult the Agile Board
        story = await self._find_matching_story(embedding)
        if not story:
            return (
                200,
                '[PFC] No relevant Epics/Stories found for this workflow. Standing down.',
            )

        # 4. Create the Tactical Ticket
        task = await self._create_task(story, routing_context, embedding)

        # 5. Hand off to the Frontal Lobe
        await self._assign_task_to_blackboard(task)

        logger.info(
            f'[PFC] Routing successful. Launching Frontal Lobe for Task {task.id}'
        )
        lobe = FrontalLobe(self.head)
        return await lobe.run()

    async def _load_context(self):
        """Loads the execution head and its hierarchical provenance."""
        # Using select_related to avoid N+1 queries when building the context string
        self.head = await sync_to_async(
            HydraHead.objects.select_related(
                'provenance', 'provenance__spell'
            ).get
        )(id=self.head_id)

        self.provenance = self.head.provenance

        # Assuming the head or provenance has an environment link based on your recent Epic change
        # Fallback to None if the model doesn't enforce it yet.
        self.environment = getattr(self.head, 'environment', None)

    def _build_routing_context(self) -> str:
        """Constructs a dense string representing the workflow intent."""
        spell_name = (
            self.provenance.spell.name
            if self.provenance.spell
            else 'Unknown Spell'
        )
        env_name = self.environment.name if self.environment else 'Global'

        # We include the Node status (e.g., 'Failed', 'Completed') to inform the vector
        # whether it should look for 'Error Triage' stories or 'Statistic Gathering' stories.
        status_name = (
            self.provenance.status.name
            if self.provenance.status
            else 'Unknown Status'
        )

        context_parts = [
            f'Environment: {env_name}',
            f'Executed Action: {spell_name}',
            f'Execution Result: {status_name}',
        ]
        return ' | '.join(context_parts)

    async def _generate_vector(self, text: str) -> list:
        """Fetches the 768-dim embedding from Ollama."""
        registry = await sync_to_async(ModelRegistry.objects.get)(
            id=ModelRegistry.NOMIC_EMBED_TEXT
        )
        client = OllamaClient(registry.name)
        return await sync_to_async(client.embed)(text)

    async def _find_matching_story(self, embedding: list) -> PFCStory | None:
        """
        Finds the closest Agile Story mathematically.
        Strictly scopes the search to the current Environment.
        """

        def _query():
            # Filter by Environment (or Global Epics where environment is null)
            qs = PFCStory.objects.filter(epic__environment=self.environment)

            # Annotate distance and filter out legacy nulls
            qs = (
                qs.exclude(vector__isnull=True)
                .annotate(distance=CosineDistance('vector', embedding))
                .order_by('distance')
            )

            return qs.first()

        best_match = await sync_to_async(_query)()

        if (
            best_match
            and getattr(best_match, 'distance', 1.0)
            <= self.MAX_ALLOWED_DISTANCE
        ):
            return best_match

        return None

    async def _create_task(
        self, story: PFCStory, context: str, embedding: list
    ) -> PFCTask:
        """Creates the executable ticket for Talos."""
        in_progress = await sync_to_async(PFCItemStatus.objects.get)(
            id=PFCItemStatus.IN_PROGRESS
        )

        spell_name = (
            self.provenance.spell.name if self.provenance.spell else 'Workflow'
        )

        return await sync_to_async(PFCTask.objects.create)(
            name=f'Review: {spell_name}',
            description=f'Triggered by workflow completion.\nContext: {context}',
            story=story,
            status=in_progress,
            vector=embedding,
        )

    async def _assign_task_to_blackboard(self, task: PFCTask):
        """Injects the Task ID into the graph execution state."""
        if not isinstance(self.head.blackboard, dict):
            self.head.blackboard = {}

        self.head.blackboard['active_pfc_task_id'] = str(task.id)
        await sync_to_async(self.head.save)(update_fields=['blackboard'])


class PrefrontalCortexDispatcher:
    """
    The Summoning Circle.
    Evaluates the Agile Board and summons the correct Character (Persona)
    to handle the current state of the studio.
    """

    def __init__(self, head_id: str):
        self.head_id = head_id
        self.head = None

    async def engage(self) -> Tuple[int, str]:
        logger.info(
            f'[PFC] Dispatcher checking the board for Head {self.head_id}'
        )

        self.head = await sync_to_async(HydraHead.objects.get)(id=self.head_id)

        # 1. Is there a Worker (Pig) ticket ready to go?
        # A Story that the Oracle (PM) has explicitly moved to 'Selected for Development'
        ready_story = await self._get_highest_priority_ready_story()

        if not isinstance(self.head.blackboard, dict):
            self.head.blackboard = {}

        if ready_story:
            logger.info(
                f"[PFC] Found active Story '{ready_story.name}'. Summoning The Automaton (Worker)."
            )
            # Lock it so another worker doesn't grab it
            ready_story.status_id = PFCItemStatus.IN_PROGRESS
            await sync_to_async(ready_story.save)(update_fields=['status_id'])

            self.head.blackboard['persona'] = 'AUTOMATON'
            self.head.blackboard['active_story_id'] = str(ready_story.id)

        else:
            logger.info(
                '[PFC] The board is empty or lacks prioritized work. Summoning The Oracle (PM).'
            )
            self.head.blackboard['persona'] = 'ORACLE'
            # The Oracle doesn't get a specific ticket; its job is the whole board.

        await sync_to_async(self.head.save)(update_fields=['blackboard'])

        # Launch the Frontal Lobe with the chosen Persona
        lobe = FrontalLobe(self.head)
        return await lobe.run()

    async def _get_highest_priority_ready_story(self):
        """Returns the oldest Story marked as 'Selected for Development'."""

        def _query():
            return (
                PFCStory.objects.filter(
                    status_id=PFCItemStatus.SELECTED_FOR_DEVELOPMENT
                )
                .order_by('modified')
                .first()
            )

        return await sync_to_async(_query)()


async def dispatch_pfc(head_id: str) -> tuple[int, str]:
    """Native execution handler for the Hydra Graph."""
    dispatcher = PrefrontalCortexDispatcher(head_id)
    return await dispatcher.engage()
