import logging
from typing import Any, Optional, Tuple

from asgiref.sync import sync_to_async
from django.db import transaction

from central_nervous_system.models import Spike
from central_nervous_system.utils import get_active_environment
from temporal_lobe.constants import TemporalConstants
from temporal_lobe.models import (
    Iteration,
    IterationShift,
    IterationShiftDefinition,
    IterationShiftParticipant,
    IterationStatus,
)

logger = logging.getLogger(__name__)


class TemporalLobe:
    """The Timekeeper: Manages the advancement of Iterations and Shifts."""

    def __init__(self, spike_id: str):
        self.spike_id = spike_id

    async def engage(self) -> Tuple[int, str]:
        """Native entry point for the CNS Graph."""

        spike = await sync_to_async(Spike.objects.get)(id=self.spike_id)
        env = await sync_to_async(get_active_environment)(spike)

        if not env:
            return 500, TemporalConstants.ERR_NO_ENV

        (
            iteration,
            active_shift,
            identity_id,
        ) = await self._calculate_current_time(env.id)

        if not iteration:
            return 200, TemporalConstants.MSG_CYCLE_COMPLETE

        from prefrontal_cortex.prefrontal_cortex import PrefrontalCortex

        compiler = PrefrontalCortex(spike.id, iteration.id, active_shift.id,
                                    identity_id)
        return await compiler.compile_and_dispatch()

    @sync_to_async
    def _calculate_current_time(
        self, env_id: str
    ) -> Tuple[Optional[Iteration], Optional[Any], Optional[str]]:
        with transaction.atomic():
            iteration = (Iteration.objects.select_for_update().filter(
                environment_id=env_id,
                status_id__in=[
                    IterationStatus.WAITING,
                    IterationStatus.RUNNING,
                ],
            ).order_by('created').first())

            if not iteration:
                return None, None, None

            if iteration.status_id == IterationStatus.WAITING:
                iteration.status_id = IterationStatus.RUNNING
                iteration.save(update_fields=['status'])

            current_shift_instance = (IterationShift.objects.select_related(
                'shift',
                'definition').filter(id=iteration.current_shift_id).first())

            # Catch initialization edge case if current_shift is null
            if not current_shift_instance:
                # We need to build the runtime shifts or grab the first definition
                return None, None, None

            active_shift = current_shift_instance.shift
            turn_limit = current_shift_instance.definition.turn_limit

            if iteration.turns_consumed_in_shift >= turn_limit:
                current_shift_instance, active_shift = self._advance_shift(
                    iteration, current_shift_instance)
                if not current_shift_instance:
                    return None, None, None

            # Pull the active participant (Disc) from the runtime instance
            participant = IterationShiftParticipant.objects.filter(
                iteration_shift=current_shift_instance).first()

            identity_id = (str(participant.iteration_participant.identity.id)
                           if participant else None)

            return iteration, active_shift, identity_id

    def _advance_shift(
        self, iteration: Iteration, current_shift_instance: IterationShift
    ) -> Tuple[Optional[IterationShift], Optional[Any]]:

        # We need the next definition based on order
        next_def = (
            IterationShiftDefinition.objects.select_related('shift').filter(
                definition=iteration.definition,
                order__gt=current_shift_instance.definition.order,
            ).order_by('order').first())

        if not next_def:
            iteration.status_id = IterationStatus.FINISHED
            iteration.save(update_fields=['status'])
            return None, None

        # Find or create the runtime instance for the next shift
        next_shift_instance, _ = IterationShift.objects.get_or_create(
            shift_iteration=iteration,
            definition=next_def,
            defaults={'shift': next_def.shift},
        )

        iteration.current_shift = next_shift_instance
        iteration.turns_consumed_in_shift = 0
        iteration.save(
            update_fields=['current_shift', 'turns_consumed_in_shift'])

        return next_shift_instance, next_shift_instance.shift


async def temporal_lobe_engage(spike_id: str) -> tuple[int, str]:
    lobe = TemporalLobe(spike_id)
    return await lobe.engage()
