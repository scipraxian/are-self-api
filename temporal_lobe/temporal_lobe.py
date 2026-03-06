import logging
from typing import Optional, Tuple

from asgiref.sync import sync_to_async
from celery.result import AsyncResult
from django.db import transaction
from django.db.models import Q

from central_nervous_system.central_nervous_system import CNS
from central_nervous_system.models import (
    NeuralPathway,
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
)
from identity.models import IdentityDisc
from temporal_lobe.models import (
    Iteration,
    IterationShift,
    IterationShiftParticipant,
    IterationShiftParticipantStatus,
    IterationStatus,
)

logger = logging.getLogger(__name__)


class TemporalLobe:
    """The pure state machine for managing Time and Workers."""

    def __init__(self, spike_id: str):
        self.spike_id = spike_id
        self.max_concurrent_workers = 1
        logger.info(f'[TemporalLobe] Temporal Lobe engaged for {spike_id}.')

    async def tick(self) -> Tuple[int, str]:
        """The heartbeat. Cleans up, checks capacity, and dispatches workers."""
        logger.info(
            f'[TemporalLobe] Ticking Temporal Lobe for {self.spike_id}.'
        )
        spike = await sync_to_async(
            Spike.objects.select_related('spike_train').get
        )(id=self.spike_id)

        # 1. Get the active Iteration
        iteration = await self._get_active_iteration(
            spike.spike_train.environment_id
        )
        if not iteration:
            return 200, 'No active iterations to manage.'

        # 2. Get the active Shift
        shift = await sync_to_async(lambda: iteration.current_shift)()
        if not shift:
            # If there's no shift set, try to advance to the first one
            shift = await self._advance_shift(iteration)
            if not shift:
                return 200, 'Iteration has no valid shifts defined.'

        # 3. Ghost Cleanup (Placeholder)
        await self._cleanup_ghost_workers(shift)

        # 4. Capacity Check
        active_count = await sync_to_async(
            IterationShiftParticipant.objects.filter(
                iteration_shift=shift,
                status_id=IterationShiftParticipantStatus.ACTIVATED,
            ).count
        )()

        if active_count >= self.max_concurrent_workers:
            return (
                200,
                f'Capacity full ({active_count}/{self.max_concurrent_workers}).',
            )

        # 5. Dispatch new workers
        slots_available = self.max_concurrent_workers - active_count
        dispatched_count = await self._dispatch_pending_workers(
            shift, slots_available, spike
        )

        # 6. Advance Shift if completely done
        if dispatched_count == 0 and active_count == 0:
            # Everyone is COMPLETED
            next_shift = await self._advance_shift(iteration)
            if next_shift:
                return (
                    200,
                    f'Shift complete. Advanced to {next_shift.shift.name}.',
                )
            else:
                return 200, 'Iteration complete. Pipeline finished.'

        return 200, f'Tick complete. Dispatched {dispatched_count} new workers.'

    @sync_to_async
    def _get_active_iteration(self, env_id: str) -> Optional[Iteration]:
        # Lock the row to prevent race conditions during the tick
        return (
            Iteration.objects.filter(
                environment_id=env_id,
                status_id__in=[
                    IterationStatus.WAITING,
                    IterationStatus.RUNNING,
                ],
            )
            .order_by('created')
            .first()
        )

    @sync_to_async
    def _advance_shift(self, iteration: Iteration) -> Optional[IterationShift]:
        """Moves the iteration to the next shift, or finishes it."""
        with transaction.atomic():
            current_shift = iteration.current_shift

            if not current_shift:
                # Grab the very first shift
                next_shift = iteration.iterationshift_set.order_by(
                    'definition__order'
                ).first()
            else:
                # Grab the next shift in the sequence
                next_shift = (
                    iteration.iterationshift_set.filter(
                        definition__order__gt=current_shift.definition.order
                    )
                    .order_by('definition__order')
                    .first()
                )

            if next_shift:
                # We have a next shift. Update the Iteration.
                iteration.current_shift = next_shift
                if iteration.status_id == IterationStatus.WAITING:
                    iteration.status_id = IterationStatus.RUNNING
                iteration.save(update_fields=['current_shift', 'status'])
                logger.info(
                    f'[TemporalLobe] Iteration {iteration.id} advanced to shift: {next_shift.shift.name}'
                )
                return next_shift
            else:
                # No more shifts. We are done.
                iteration.status_id = IterationStatus.FINISHED
                iteration.current_shift = None
                iteration.save(update_fields=['status', 'current_shift'])

                # Release the clone army back to the barracks

                participants = iteration.iterationshift_set.values_list(
                    'iterationshiftparticipant__iteration_participant',
                    flat=True,
                )
                IdentityDisc.objects.filter(
                    id__in=[p for p in participants if p]
                ).update(available=True)

                logger.info(
                    f'[TemporalLobe] Iteration {iteration.id} completely finished.'
                )
                return None

    @sync_to_async
    def _lock_and_get_pending_participants(self, shift_id, slots):
        with transaction.atomic():
            pending_workers = (
                IterationShiftParticipant.objects.select_for_update()
                .filter(
                    Q(iteration_shift_id=shift_id),
                    (
                        Q(status_id=IterationShiftParticipantStatus.SELECTED)
                        | Q(status__isnull=True)
                    ),
                )
                .order_by('id')[:slots]
            )

            dispatched_ids = []
            for iteration_shift_participant in pending_workers:
                iteration_shift_participant.status_id = (
                    IterationShiftParticipantStatus.ACTIVATED
                )
                iteration_shift_participant.save(update_fields=['status'])
                dispatched_ids.append(iteration_shift_participant.id)
                logger.info(
                    f'[TemporalLobe] Locked {
                        iteration_shift_participant.iteration_participant.name
                    } for dispatch.'
                )

            return dispatched_ids

    async def _dispatch_pending_workers(
        self, shift, slots, parent_spike
    ) -> int:
        logger.info(
            f'[TemporalLobe] Dispatching pending workers for {parent_spike.id}.'
        )

        # 1. Grab the locked IDs safely from the synchronous DB thread
        iteration_shift_participant_ids = (
            await self._lock_and_get_pending_participants(shift.id, slots)
        )

        logger.info(
            f'[TemporalLobe] Locked IDs: {len(iteration_shift_participant_ids)}'
        )

        if not iteration_shift_participant_ids:
            return 0

        # Not sure about circular. Check and move if possible.
        from prefrontal_cortex.prefrontal_cortex import PrefrontalCortex

        pfc = PrefrontalCortex(parent_spike.id)

        # 2. Execute the async dispatches in the event loop!
        for worker_id in iteration_shift_participant_ids:
            await pfc.dispatch(worker_id)
            logger.info(
                f'[TemporalLobe] Dispatched disc {worker_id} to the PFC.'
            )

        return len(iteration_shift_participant_ids)

    @sync_to_async
    def _cleanup_ghost_workers(self, shift):
        """Placeholder for future cleanup logic."""
        pass


def fetch_canonical_temporal_pathway():
    """Contained in initial_data.json fixture."""
    return NeuralPathway.objects.get(id='c3dd041a-20eb-4414-b571-2a5fdbeb9b86')


async def run_temporal_lobe(spike_id: str) -> Tuple[int, str]:
    """Engage the Temporal Lobe to process a spike."""
    lobe = TemporalLobe(spike_id)
    return await lobe.tick()


def trigger_temporal_metronomes() -> list:
    pathway = fetch_canonical_temporal_pathway()
    spawned_trains = []

    # =========================================================================
    # STEP 1: CELERY-FIRST GARBAGE COLLECTION
    # =========================================================================
    active_metronomes = SpikeTrain.objects.filter(
        pathway=pathway,
        status_id__in=[SpikeTrainStatus.CREATED, SpikeTrainStatus.RUNNING]
    )

    for train in active_metronomes:
        # Get the active execution nodes for this train
        active_spikes = train.spikes.filter(
            status_id__in=[SpikeStatus.RUNNING, SpikeStatus.PENDING]
        )

        is_truly_alive = False

        for spike in active_spikes:
            if spike.celery_task_id:
                res = AsyncResult(str(spike.celery_task_id))
                # Ask Celery for the absolute truth
                if res.state in ['PENDING', 'STARTED', 'RECEIVED', 'RETRY']:
                    is_truly_alive = True
                    break  # We found a healthy pulse, no need to check other spikes

        if is_truly_alive:
            # Hands completely off. It's doing its job.
            continue

        # If we get here, the DB says RUNNING, but Celery has absolutely no idea what we are talking about.
        # It's a system crash ghost. NOW we wake up the Orchestrator to clean up the DB.
        logger.warning(
            f"[HEARTBEAT] System Crash Ghost detected for SpikeTrain {train.id}. Triggering GC.")
        try:
            cns = CNS(spike_train_id=train.id)
            cns.poll()  # This will mark the spikes FAILED and cascade the train to a stopped state
        except Exception as e:
            logger.error(
                f"[HEARTBEAT] Error cleaning ghost SpikeTrain {train.id}: {e}")

    # =========================================================================
    # STEP 2: SPAWN MISSING METRONOMES
    # =========================================================================
    active_environments = Iteration.objects.filter(
        status_id__in=[IterationStatus.WAITING, IterationStatus.RUNNING]
    ).values_list('environment_id', flat=True).distinct()

    if not active_environments:
        return []

    for env_id in active_environments:
        # THE BOUNCER: Is there already a Metronome running for this project?
        # (It might have just been cleared by the ghost protocol above!)
        is_already_running = SpikeTrain.objects.filter(
            pathway=pathway,
            environment_id=env_id,
            status_id__in=[SpikeTrainStatus.CREATED, SpikeTrainStatus.RUNNING]
        ).exists()

        if is_already_running:
            continue

        # Safe to spawn!
        spike_train = SpikeTrain.objects.create(
            pathway=pathway,
            environment_id=env_id,
            status_id=SpikeTrainStatus.CREATED
        )

        cns = CNS(spike_train_id=spike_train.id)
        cns.start()

        spawned_trains.append(spike_train.id)
        logger.info(
            f"[HEARTBEAT] Fired for Environment {env_id}: SpikeTrain {spike_train.id}")

    return spawned_trains