import logging
import uuid

from asgiref.sync import sync_to_async
from django.db import transaction

from central_nervous_system.models import Spike
from frontal_lobe.frontal_lobe import FrontalLobe
from frontal_lobe.models import ReasoningSession, ReasoningStatusID
from identity.models import IdentityType
from prefrontal_cortex.models import PFCEpic, PFCItemStatus, PFCStory, PFCTask
from temporal_lobe.models import IterationShiftParticipant, Shift

logger = logging.getLogger(__name__)


class PrefrontalCortex:
    def __init__(self, spike_id: uuid.UUID):
        self.spike_id = spike_id
        self.spike = None

    @classmethod
    def get_work_query_params(
        cls, shift_id: int, identity_type_id: int, environment_id: str
    ) -> tuple:
        """
        The absolute source of truth for mapping Shifts & Identities to Agile Models.
        Returns (ModelClass, query_kwargs, order_by_field)
        """
        kwargs = {}

        if identity_type_id == IdentityType.PM:
            if shift_id == Shift.GROOMING:
                kwargs['status_id__in'] = [
                    PFCItemStatus.NEEDS_REFINEMENT,
                    PFCItemStatus.BACKLOG,
                ]
                if environment_id:
                    kwargs['environment_id'] = environment_id
                return PFCEpic, kwargs, '-priority'

            if shift_id in [Shift.PRE_PLANNING, Shift.PLANNING]:
                kwargs['status_id__in'] = [
                    PFCItemStatus.NEEDS_REFINEMENT,
                ]
                if environment_id:
                    kwargs['epic__environment_id'] = environment_id
                return PFCStory, kwargs, '-priority'

        elif identity_type_id == IdentityType.WORKER:
            if shift_id == Shift.EXECUTING:
                kwargs['status_id__in'] = [
                    PFCItemStatus.SELECTED_FOR_DEVELOPMENT,
                ]
                if environment_id:
                    kwargs['story__epic__environment_id'] = environment_id
                # PFCTask lacks 'priority', so we pull the oldest tasks first
                return PFCTask, kwargs, 'created'

        return None, None, None

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

        # 1. Attempt to lock a ticket FOR THIS SPECIFIC WORKER
        assigned_item = await self._assign_ticket(
            shift_id=participant.iteration_shift.shift.id,
            identity_type_id=participant.iteration_participant.identity.identity_type_id,
            identity_disc=participant.iteration_participant,
            environment_id=environment_id,
        )

        # THE BOUNCER: If there is no work, we STOP here. No Frontal Lobe is spun up.
        if not assigned_item:
            logger.info(
                f'[PFC] No actionable work found for {participant.iteration_participant.name}. Standing down.'
            )
            return None

        # 2. Work exists and is locked! Spin up the Frontal Lobe.
        return await self._create_session_and_run(
            participant.iteration_shift,
            participant.iteration_participant,
            participant,
            assigned_item,
        )

    async def _create_session_and_run(
        self, iteration_shift, identity_disc, participant, assigned_item
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

        # The AI is now awake and will read the assigned ticket via the Agile Addon
        await lobe.run()

        # Cleanup: Remove the owning disc and push to previous owners
        if assigned_item:
            await self._release_ticket(assigned_item, identity_disc)

        return lobe.session.id

    @sync_to_async
    def _assign_ticket(
        self,
        shift_id: int,
        identity_type_id: int,
        identity_disc,
        environment_id: str,
    ):
        """Finds the highest priority ticket, preferring ones this disc previously owned. Locks it."""
        logger.info(
            f'Assigning ticket for shift {shift_id} and identity type {identity_type_id}'
        )
        model_class, kwargs, order_field = self.get_work_query_params(
            shift_id, identity_type_id, environment_id
        )
        if not model_class:
            return None

        with transaction.atomic():
            # Strategy 1: Reclaim a previously owned ticket that is currently unassigned
            item = (
                model_class.objects.select_for_update()
                .filter(
                    previous_owners=identity_disc,
                    owning_disc__isnull=True,
                    **kwargs,
                )
                .order_by(order_field)
                .first()
            )

            # Strategy 2: Grab the highest priority unassigned ticket
            if not item:
                item = (
                    model_class.objects.select_for_update()
                    .filter(owning_disc__isnull=True, **kwargs)
                    .order_by(order_field)
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
            else:
                logger.info(
                    f'[PFC] No actionable work found for {identity_disc.name}.'
                )
            return None

    @sync_to_async
    def _release_ticket(self, item, identity_disc):
        """Removes the active lock and logs the historical touch."""
        item.owning_disc = None
        item.save(update_fields=['owning_disc'])
        item.previous_owners.add(identity_disc)
        logger.info(
            f'[PFC] Released {item.__class__.__name__} {item.id} from {identity_disc.name}'
        )
