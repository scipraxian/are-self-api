import logging
import uuid

from asgiref.sync import sync_to_async
from django.db.models import Q
from django.utils import timezone

from central_nervous_system.models import Spike
from frontal_lobe.frontal_lobe import FrontalLobe
from frontal_lobe.models import ReasoningSession, ReasoningStatusID
from identity.models import IdentityType
from prefrontal_cortex.models import PFCEpic, PFCItemStatus, PFCStory, PFCTask
from temporal_lobe.models import (
    IterationShiftParticipant,
    IterationShiftParticipantStatus,
    Shift,
)

logger = logging.getLogger(__name__)


def lock_ticket(ticket, identity_disc):
    ticket.owning_disc = identity_disc
    ticket.save(update_fields=['owning_disc'])
    logger.debug(
        f'[PFC] Locked {ticket.__class__.__name__} {ticket.id} to {identity_disc.name}'
    )
    return True


class PrefrontalCortex:
    def __init__(self, spike_id: uuid.UUID = None):
        self.spike_id = spike_id
        self.spike = None

    @classmethod
    async def has_actionable_work_in_environment(
        cls, environment_id: uuid.UUID
    ) -> bool:
        """Global pre-check for the Temporal Lobe before spawning a SpikeTrain."""
        # Quick check: Is there ANYTHING not done or blocked?
        pending_epics = (
            await PFCEpic.objects.filter(
                environment=environment_id,
            )
            .exclude(
                status_id__in=[
                    PFCItemStatus.DONE,
                    PFCItemStatus.WILL_NOT_DO,
                    PFCItemStatus.BLOCKED_BY_USER,
                ]
            )
            .acount()
        )

        pending_stories = (
            await PFCStory.objects.filter(
                epic__environment_id=environment_id,
            )
            .exclude(
                status_id__in=[
                    PFCItemStatus.DONE,
                    PFCItemStatus.WILL_NOT_DO,
                    PFCItemStatus.BLOCKED_BY_USER,
                ]
            )
            .acount()
        )

        pending_tasks = (
            await PFCTask.objects.filter(
                story__epic__environment_id=environment_id,
            )
            .exclude(
                status_id__in=[PFCItemStatus.DONE, PFCItemStatus.WILL_NOT_DO]
            )
            .acount()
        )

        return (pending_epics + pending_stories + pending_tasks) > 0

    @sync_to_async
    def _garbage_collect_locks(self, identity_disc):
        """Releases locks on anything this disc owned that was left hanging from a previous shift."""
        # 1. Revert anything left IN_PROGRESS back to SELECTED_FOR_DEVELOPMENT
        PFCTask.objects.filter(
            owning_disc=identity_disc, status_id=PFCItemStatus.IN_PROGRESS
        ).update(
            status_id=PFCItemStatus.SELECTED_FOR_DEVELOPMENT, owning_disc=None
        )

        # 2. Release all other locks purely
        PFCEpic.objects.filter(owning_disc=identity_disc).update(
            owning_disc=None
        )
        PFCStory.objects.filter(owning_disc=identity_disc).update(
            owning_disc=None
        )
        PFCTask.objects.filter(owning_disc=identity_disc).update(
            owning_disc=None
        )
        logger.debug(
            f'[PFC] Garbage collected old locks for {identity_disc.name}.'
        )

    @sync_to_async
    def _assign_work(
        self,
        shift_id: int,
        identity_type_id: int,
        identity_disc,
        environment_id: uuid.UUID,
    ) -> bool:
        """Finds the highest priority ticket for the shift and strictly locks it to the disc."""

        if shift_id == Shift.SIFTING:
            if identity_type_id == IdentityType.PM:
                target = PFCEpic.objects.filter(
                    status_id=PFCItemStatus.NEEDS_REFINEMENT,
                    environment=environment_id,
                ).first()
                if not target:
                    target = PFCStory.objects.filter(
                        status_id=PFCItemStatus.NEEDS_REFINEMENT,
                        epic__environment_id=environment_id,
                    ).first()
                if target:
                    return lock_ticket(target, identity_disc)
            elif identity_type_id == IdentityType.WORKER:
                target = PFCStory.objects.filter(
                    status_id=PFCItemStatus.BACKLOG,
                    owning_disc__isnull=True,
                    epic__environment_id=environment_id,
                    complexity=0,
                ).first()
                if target:
                    return lock_ticket(target, identity_disc)

        elif shift_id == Shift.PRE_PLANNING:
            if identity_type_id == IdentityType.PM:
                target = PFCEpic.objects.filter(
                    status_id=PFCItemStatus.BACKLOG, environment=environment_id
                ).first()
                if not target:
                    target = PFCStory.objects.filter(
                        status_id=PFCItemStatus.BACKLOG,
                        epic__environment_id=environment_id,
                    ).first()
                if target:
                    return lock_ticket(target, identity_disc)
            elif identity_type_id == IdentityType.WORKER:
                target = PFCStory.objects.filter(
                    status_id=PFCItemStatus.SELECTED_FOR_DEVELOPMENT,
                    owning_disc__isnull=True,
                    epic__environment_id=environment_id,
                ).first()
                if target:
                    return lock_ticket(target, identity_disc)

        elif shift_id == Shift.EXECUTING:
            if identity_type_id == IdentityType.WORKER:
                # Execution: Grab tasks that are Selected.
                target = PFCTask.objects.filter(
                    status_id=PFCItemStatus.SELECTED_FOR_DEVELOPMENT,
                    owning_disc__isnull=True,
                    story__epic__environment_id=environment_id,
                ).first()
                if target:
                    return lock_ticket(target, identity_disc)

        elif shift_id == Shift.POST_EXECUTION:
            if identity_type_id == IdentityType.PM:
                target = PFCStory.objects.filter(
                    status_id=PFCItemStatus.IN_REVIEW,
                    epic__environment_id=environment_id,
                ).first()
                if target:
                    return lock_ticket(target, identity_disc)
            elif identity_type_id == IdentityType.WORKER:
                target = PFCTask.objects.filter(
                    status_id=PFCItemStatus.IN_REVIEW,
                    story__epic__environment_id=environment_id,
                ).first()
                if target:
                    return lock_ticket(target, identity_disc)

        return False

    async def dispatch(
        self, iteration_shift_participant_id: int, environment_id: uuid.UUID
    ):
        logger.debug(
            f'[PFC] Dispatching for {iteration_shift_participant_id} in spike {self.spike_id}.'
        )

        self.spike = await sync_to_async(
            Spike.objects.select_related('spike_train').get
        )(id=self.spike_id)
        participant = await sync_to_async(
            IterationShiftParticipant.objects.select_related(
                'iteration_shift__shift',
                'iteration_shift__definition',
                'iteration_participant__identity_type',
            ).get
        )(id=iteration_shift_participant_id)

        identity_disc = participant.iteration_participant

        # 1. Clean up old locks
        await self._garbage_collect_locks(identity_disc)

        # 2. Assign and Lock new work
        is_assigned = await self._assign_work(
            shift_id=participant.iteration_shift.shift.id,
            identity_type_id=identity_disc.identity_type_id,
            identity_disc=identity_disc,
            environment_id=environment_id,
        )

        # 3. The Bouncer
        if not is_assigned:
            logger.debug(
                f'[PFC] No actionable work found for {identity_disc.name}. Standing down.'
            )
            return None

        # 4. Wake up
        return await self._create_session_and_run(
            participant.iteration_shift, identity_disc, participant
        )

    async def _create_session_and_run(
        self, iteration_shift, identity_disc, participant
    ):
        logger.info(f'[PFC] Starting Session for {identity_disc.name}.')
        lobe = FrontalLobe(self.spike)
        lobe.session = await sync_to_async(ReasoningSession.objects.create)(
            spike=self.spike,
            status_id=ReasoningStatusID.ACTIVE,
            max_turns=iteration_shift.definition.turn_limit,
            identity_disc=identity_disc,
            participant=participant,
        )
        await lobe.run()

        participant.status_id = IterationShiftParticipantStatus.COMPLETED
        await sync_to_async(participant.save)(update_fields=['status'])
        return lobe.session.id
