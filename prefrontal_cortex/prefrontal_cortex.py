import logging
import uuid

from asgiref.sync import sync_to_async

from central_nervous_system.models import Spike
from frontal_lobe.frontal_lobe import FrontalLobe
from frontal_lobe.models import ReasoningSession, ReasoningStatusID
from identity.models import IdentityType
from prefrontal_cortex.models import PFCEpic, PFCItemStatus, PFCStory, PFCTask
from temporal_lobe.models import IterationShiftParticipant, Shift

logger = logging.getLogger(__name__)


class PrefrontalCortex:
    """The Compiler: Translates Time into Context and dispatches the execution graph."""

    def __init__(self, spike_id: uuid.UUID):
        self.spike = Spike.objects.get(id=spike_id)

    async def dispatch(self, iteration_shift_participant_id: int):
        iteration_shift_participant = await sync_to_async(
            IterationShiftParticipant.objects.select_related(
                'iteration_shift__shift', 'iteration_participant__identity'
            ).get
        )(id=iteration_shift_participant_id)

        iteration_shift = iteration_shift_participant.iteration_shift
        identity_disc = iteration_shift_participant.iteration_participant

        return await self._create_session_and_run(
            iteration_shift, identity_disc, iteration_shift_participant
        )

    async def _create_session_and_run(
        self, iteration_shift, identity_disc, iteration_shift_participant
    ):
        """Finds the Frontal Lobe graph, locks a ticket, and spins up the asynchronous SpikeTrain."""

        # 1. Pick and assign the ticket
        assigned_item = await self._assign_ticket(
            shift_id=iteration_shift.shift.id,
            identity_type_id=identity_disc.identity.identity_type_id,
            identity_disc=identity_disc,
        )

        # 2. Setup the Frontal Lobe
        lobe = FrontalLobe(self.spike)
        lobe.session = await sync_to_async(
            ReasoningSession.objects.create
        )(
            spike=self.spike,
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=iteration_shift.definition.turn_limit,  # Note: using turn_limit from your models
            identity_disc=identity_disc,
            participant=iteration_shift_participant,
        )

        # 3. Run the session (The AI is now awake and will read the assigned ticket via the Addon)
        await lobe.run()

        # 4. Cleanup: Remove the owning disc and push to previous owners
        if assigned_item:
            await self._release_ticket(assigned_item, identity_disc)

        return lobe.session.id

    @sync_to_async
    def _assign_ticket(
        self, shift_id: int, identity_type_id: int, identity_disc
    ):
        """Finds the highest priority ticket, preferring ones this disc previously owned."""
        model_class = None
        valid_statuses = []

        # Determine the target pool
        if identity_type_id == IdentityType.PM:
            if shift_id == Shift.GROOMING:
                model_class = PFCEpic
                valid_statuses = [
                    PFCItemStatus.NEEDS_REFINEMENT,
                    PFCItemStatus.BACKLOG,
                ]
            elif shift_id in [Shift.PRE_PLANNING, Shift.PLANNING]:
                model_class = PFCStory
                valid_statuses = [
                    PFCItemStatus.NEEDS_REFINEMENT,
                    PFCItemStatus.BACKLOG,
                ]
        elif identity_type_id == IdentityType.WORKER:
            if shift_id == Shift.EXECUTING:
                model_class = PFCTask
                valid_statuses = [
                    PFCItemStatus.BACKLOG,
                    PFCItemStatus.SELECTED_FOR_DEVELOPMENT,
                ]

        if not model_class:
            return None

        # Strategy 1: Reclaim a previously owned ticket that is currently unassigned
        item = (
            model_class.objects.filter(
                previous_owners=identity_disc,
                owning_disc__isnull=True,
                status_id__in=valid_statuses,
            )
            .order_by('-priority')
            .first()
        )

        # Strategy 2: Grab the highest priority unassigned ticket
        if not item:
            item = (
                model_class.objects.filter(
                    owning_disc__isnull=True, status_id__in=valid_statuses
                )
                .order_by('-priority')
                .first()
            )

        # Lock it in!
        if item:
            item.owning_disc = identity_disc
            item.save(update_fields=['owning_disc'])
            logger.info(
                f'[PFC] Locked {item.__class__.__name__} {item.id} to {identity_disc.name}'
            )

        return item

    @sync_to_async
    def _release_ticket(self, item, identity_disc):
        """Removes the active lock and logs the historical touch."""
        item.owning_disc = None
        item.save(update_fields=['owning_disc'])
        item.previous_owners.add(identity_disc)
        logger.info(
            f'[PFC] Released {item.__class__.__name__} {item.id} from {identity_disc.name}'
        )
