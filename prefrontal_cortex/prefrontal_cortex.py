import logging
import uuid

from asgiref.sync import sync_to_async
from django.db.models import Q

from central_nervous_system.models import Spike
from frontal_lobe.frontal_lobe import FrontalLobe
from frontal_lobe.models import ReasoningSession, ReasoningStatusID
from identity.models import IdentityType
from prefrontal_cortex.models import PFCEpic, PFCItemStatus, PFCStory
from temporal_lobe.models import IterationShiftParticipant, Shift

logger = logging.getLogger(__name__)


async def sifting_pm(identity_disc, environment_id) -> bool:
    """The Sifting PM reviews work and moves it to the backlog."""
    epics = PFCEpic.objects.filter(
        (
            Q(status_id=PFCItemStatus.NEEDS_REFINEMENT)
            | Q(status_id=PFCItemStatus.BACKLOG)
        )
        & Q(environment=environment_id)
    )
    if epics.count():
        return True

    stories = PFCStory.objects.filter(
        (
            Q(status_id=PFCItemStatus.NEEDS_REFINEMENT)
            | Q(status_id=PFCItemStatus.BACKLOG)
        )
        & Q(epic__environment_id=environment_id)
    )
    if stories.count():
        return True
    return False


async def pre_planning_pm(identity_disc, environment_id) -> bool:
    """The Planning PM queries the entire board and chooses what is selected
    for development."""
    return await sifting_pm(identity_disc, environment_id)


async def planning_pm(identity_disc, environment_id) -> bool:
    """The Planning PM has no role."""
    return await sifting_pm(identity_disc, environment_id)


async def executing_pm(identity_disc, environment_id) -> bool:
    """The Executing PM has no role."""
    return await sifting_pm(identity_disc, environment_id)


async def post_execution_pm(identity_disc, environment_id) -> bool:
    """The Post execution PM reviews work and sets to blocked
    by user if it meets DoD else selected for development."""
    return (
        PFCStory.objects.filter(
            Q(status_id=PFCItemStatus.IN_REVIEW)
            & Q(epic__environment_id=environment_id)
            & (Q(owning_disc__isnull=True) | Q(owning_disc=identity_disc))
        ).count()
        > 0
    )


async def sleeping_pm(identity_disc, environment_id) -> bool:
    """The Sleeping PM has no tickets."""
    return True


async def sifting_worker(identity_disc, environment_id) -> bool:
    """The Sifting Worker cleans items in the backlog and/or
    Tasks to complete existing Stories."""
    return (
        PFCStory.objects.filter(
            (
                Q(status_id=PFCItemStatus.NEEDS_REFINEMENT)
                | Q(status_id=PFCItemStatus.BACKLOG)
            )
            & Q(owning_disc__isnull=True)
            | Q(owning_disc=identity_disc)
            & Q(epic__environment_id=environment_id)
        ).count()
        > 0
    )


async def bidding_worker(identity_disc, environment_id) -> bool:
    """The Worker BIDs on the backlog."""
    stories = PFCStory.objects.filter(
        Q(status_id=PFCItemStatus.BACKLOG)
        & Q(owning_disc__isnull=True)
        & Q(epic__environment_id=environment_id)
        & Q(complexity=0)
    )
    if stories.count():
        return True
    else:
        return await sifting_worker(identity_disc, environment_id)


async def executing_worker(identity_disc, environment_id) -> bool:
    """The Executing Worker is assigned or continues work on assigned tickets."""
    my_stories = PFCStory.objects.filter(
        Q(status_id=PFCItemStatus.SELECTED_FOR_DEVELOPMENT)
        & Q(owning_disc=identity_disc)
        & Q(epic__environment_id=environment_id)
    )
    if my_stories.count():
        return True
    available_stories = PFCStory.objects.filter(
        Q(status_id=PFCItemStatus.SELECTED_FOR_DEVELOPMENT)
        & Q(owning_disc__isnull=True)
        & Q(epic__environment_id=environment_id)
    )
    if available_stories.count():
        return True
    return False


async def sleeping_worker(identity_disc, environment_id) -> bool:
    """The Sleeping Worker has no tickets."""
    return True


async def _is_available_work(
    shift_id: int,
    identity_type_id: int,
    identity_disc,
    environment_id: str,
) -> bool:
    """Is there appropriate work for myself."""
    logger.info(
        f'Assigning ticket for shift {shift_id} and identity type {identity_type_id}'
    )
    match shift_id:
        case Shift.SIFTING:
            match identity_type_id:
                case IdentityType.PM:
                    return await sifting_pm(identity_disc, environment_id)
                case IdentityType.WORKER:
                    return await bidding_worker(identity_disc, environment_id)
        case Shift.PRE_PLANNING:
            match identity_type_id:
                case IdentityType.PM:
                    return await pre_planning_pm(identity_disc, environment_id)
                case IdentityType.WORKER:
                    return await sifting_worker(identity_disc, environment_id)
        case Shift.PLANNING:
            match identity_type_id:
                case IdentityType.PM:
                    return await planning_pm(identity_disc, environment_id)
                case IdentityType.WORKER:
                    return await sifting_worker(identity_disc, environment_id)
        case Shift.EXECUTING:
            match identity_type_id:
                case IdentityType.PM:
                    return await executing_pm(identity_disc, environment_id)
                case IdentityType.WORKER:
                    return await executing_worker(identity_disc, environment_id)
        case Shift.POST_EXECUTION:
            match identity_type_id:
                case IdentityType.PM:
                    return await post_execution_pm(
                        identity_disc, environment_id
                    )
                case IdentityType.WORKER:
                    return await bidding_worker(identity_disc, environment_id)
        case Shift.SLEEPING:
            match identity_type_id:
                case IdentityType.PM:
                    return await sleeping_pm(identity_disc, environment_id)
                case IdentityType.WORKER:
                    return await sleeping_worker(identity_disc, environment_id)


class PrefrontalCortex:
    def __init__(self, spike_id: uuid.UUID):
        self.spike_id = spike_id
        self.spike = None

    async def dispatch(
        self, iteration_shift_participant_id: int, environment_id: str
    ):
        """The Handshake: Evaluates work, assigns it, and optionally wakes the Frontal Lobe."""
        logger.info(
            f'[PFC] Dispatching for {iteration_shift_participant_id} in spike {self.spike_id}.'
        )

        self.spike = await sync_to_async(
            Spike.objects.select_related('spike_train').get
        )(id=self.spike_id)

        participant = await sync_to_async(
            IterationShiftParticipant.objects.select_related(
                'iteration_shift__shift',
                'iteration_shift__definition',
                'iteration_participant__identity',
            ).get
        )(id=iteration_shift_participant_id)

        # 1. Attempt to look for work.
        is_available_work = await _is_available_work(
            shift_id=participant.iteration_shift.shift.id,
            identity_type_id=participant.iteration_participant.identity.identity_type_id,
            identity_disc=participant.iteration_participant,
            environment_id=environment_id,
        )

        # THE BOUNCER: If there is no work, we STOP here. No Frontal Lobe is spun up.
        if not is_available_work:
            logger.info(
                f'[PFC] No actionable work found for {participant.iteration_participant.name}. Standing down.'
            )
            return None

        return await self._create_session_and_run(
            participant.iteration_shift,
            participant.iteration_participant,
            participant,
        )

    async def _create_session_and_run(
        self, iteration_shift, identity_disc, participant
    ):
        """Wakes the AI now that a ticket is firmly in hand."""
        lobe = FrontalLobe(self.spike)
        lobe.session = await sync_to_async(ReasoningSession.objects.create)(
            spike=self.spike,
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=iteration_shift.definition.turn_limit,
            identity_disc=identity_disc,
            participant=participant,
        )
        await lobe.run()
        return lobe.session.id

    @sync_to_async
    def _release_ticket(self, item, identity_disc):
        """Removes the active lock and logs the historical touch."""
        item.owning_disc = None
        item.save(update_fields=['owning_disc'])
        item.previous_owners.add(identity_disc)
        logger.info(
            f'[PFC] Released {item.__class__.__name__} {item.id} from {identity_disc.name}'
        )
