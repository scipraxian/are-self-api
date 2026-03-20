import logging
from datetime import timedelta
from typing import Optional, Tuple
from uuid import UUID

from asgiref.sync import sync_to_async
from celery import current_app, states
from celery.result import AsyncResult
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django_celery_results.models import TaskResult

from central_nervous_system.central_nervous_system import CNS
from central_nervous_system.models import (
    NeuralPathway,
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
)
from frontal_lobe.models import ReasoningSession, ReasoningStatusID
from identity.models import IdentityDisc
from temporal_lobe.models import (
    Iteration,
    IterationShift,
    IterationShiftParticipant,
    IterationShiftParticipantStatus,
    IterationStatus,
)

logger = logging.getLogger(__name__)
from asgiref.sync import async_to_sync

from prefrontal_cortex.prefrontal_cortex import PrefrontalCortex


def get_or_create_environment_trains(
    active_iteration_environments: list[UUID],
) -> list[UUID]:
    train_list = []
    pathway = fetch_canonical_temporal_pathway()
    for env_id in active_iteration_environments:
        # --- THE NEW PRE-CHECK ---
        # Don't even start the clock if the board is completely empty or stalled.
        has_work = async_to_sync(
            PrefrontalCortex.has_actionable_work_in_environment
        )(env_id)
        if not has_work:
            logger.debug(
                f'[TemporalLobe] Environment {env_id} board is empty. Skipping metronome.'
            )
            continue
        # -------------------------

        trains = SpikeTrain.objects.filter(
            pathway=pathway,
            environment_id=env_id,
            status_id__in=[SpikeTrainStatus.CREATED, SpikeTrainStatus.RUNNING],
        )
        is_already_running = trains.exists()
        if is_already_running:
            logger.debug(
                f'[TemporalLobe] SpikeTrain for Environment {env_id} is already running.'
            )
            train_list.extend(trains.values_list('id', flat=True))
            continue

        spike_train = SpikeTrain.objects.create(
            pathway=pathway,
            environment_id=env_id,
            status_id=SpikeTrainStatus.CREATED,
        )
        logger.debug(
            f'[TemporalLobe] Created new SpikeTrain {spike_train.id} for Environment {env_id}'
        )

        cns = CNS(spike_train_id=spike_train.id)
        cns.start()
        train_list.append(spike_train.id)

    return train_list


class TemporalLobe:
    """The pure state machine for managing Time and Workers."""

    def __init__(self, spike_id: str):
        self.spike_id = spike_id
        self.max_concurrent_workers = 1
        logger.debug(f'[TemporalLobe] Temporal Lobe engaged for {spike_id}.')

    async def tick(self) -> Tuple[int, str]:
        """The TemporalLobe. Cleans up, checks capacity, and dispatches workers."""
        logger.debug(
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
    def _get_active_iteration(
        self, environment_id: UUID
    ) -> Optional[Iteration]:
        # Lock the row to prevent race conditions during the tick
        return (
            Iteration.objects.filter(
                environment_id=environment_id,
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
                logger.debug(
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

                logger.debug(
                    f'[TemporalLobe] Iteration {iteration.id} completely finished.'
                )

                # ----------------------------------------------------
                # AUTO-INCEPT THE NEXT LOOP
                # ----------------------------------------------------
                from temporal_lobe.inception import IterationInceptionManager

                new_iteration = IterationInceptionManager.incept_iteration(
                    definition_id=iteration.definition_id,
                    environment_id=iteration.environment_id,
                )

                logger.debug(
                    f'[TemporalLobe] Ouroboros Protocol: Auto-incepted new Iteration loop {new_iteration.id}'
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
                logger.debug(
                    f'[TemporalLobe] Locked {
                        iteration_shift_participant.iteration_participant.name
                    } for dispatch.'
                )

            return dispatched_ids

    async def _dispatch_pending_workers(
        self, shift, slots, parent_spike
    ) -> int:
        logger.debug(
            f'[TemporalLobe] Dispatching pending workers for {parent_spike.id}.'
        )

        # 1. Grab the locked IDs safely from the synchronous DB thread
        iteration_shift_participant_ids = (
            await self._lock_and_get_pending_participants(shift.id, slots)
        )

        if not iteration_shift_participant_ids:
            return 0

        # todo: remove I really don't like this local import.
        from prefrontal_cortex.prefrontal_cortex import PrefrontalCortex

        pfc = PrefrontalCortex(parent_spike.id)

        dispatched_count = 0
        env_id = parent_spike.spike_train.environment_id

        # 2. Execute the async dispatches
        for worker_id in iteration_shift_participant_ids:
            # We pass the environment ID through to the PFC!
            session_id = await pfc.dispatch(worker_id, env_id)

            if session_id:
                logger.debug(
                    f'[TemporalLobe] Dispatched disc {worker_id} to the PFC.'
                )
                dispatched_count += 1
            else:
                # The Bouncer hit. No work available. Revert the worker status.
                logger.debug(
                    f'[TemporalLobe] Worker {worker_id} stood down (No tasks available).'
                )
                await self._stand_down_worker(worker_id)

        return dispatched_count

    @sync_to_async
    def _stand_down_worker(self, participant_id: int):
        """Reverts an ACTIVATED worker back to SELECTED if the PFC rejected the dispatch."""
        try:
            participant = IterationShiftParticipant.objects.get(
                id=participant_id
            )
            participant.status_id = IterationShiftParticipantStatus.SELECTED
            participant.save(update_fields=['status'])
        except IterationShiftParticipant.DoesNotExist:
            pass

    @sync_to_async
    def _cleanup_ghost_workers(self, shift):
        """Cleans up workers that are marked ACTIVATED but have no TRULY running ReasoningSession."""
        active_participants = IterationShiftParticipant.objects.filter(
            iteration_shift=shift,
            status_id=IterationShiftParticipantStatus.ACTIVATED,
        )

        for p in active_participants:
            is_running = False

            # Find any sessions that claim to be active
            active_sessions = ReasoningSession.objects.filter(
                participant=p,
                status_id__in=[
                    ReasoningStatusID.PENDING,
                    ReasoningStatusID.ACTIVE,
                ],
            ).select_related('spike', 'spike__status')

            for session in active_sessions:
                # TRUTH VERIFICATION: Check the underlying Spike and Celery Task
                if session.spike:
                    # 1. Did the Orchestrator already declare this spike dead?
                    if session.spike.status_id in [
                        SpikeStatus.FAILED,
                        SpikeStatus.ABORTED,
                        SpikeStatus.STOPPED,
                    ]:
                        logger.warning(
                            f'[TemporalLobe] Ghost Session {session.id}: Parent spike is {session.spike.status.name}.'
                        )
                        session.status_id = ReasoningStatusID.ERROR
                        session.save(update_fields=['status'])
                        continue  # Check next session, this one is dead

                    # 2. Does Celery actually know about this task?
                    if not _is_spike_alive(session.spike):
                        logger.warning(
                            f'[TemporalLobe] Ghost Session {session.id}: Celery task is dead.'
                        )
                        session.status_id = ReasoningStatusID.ERROR
                        session.save(update_fields=['status'])
                        continue  # Dead!

                # If we passed the gauntlet, it's genuinely running
                is_running = True
                break

            if is_running:
                continue  # All good, leave them alone

            # If we get here, no sessions are actively running in reality.
            # Did they finish successfully in a past run?
            is_done = ReasoningSession.objects.filter(
                participant=p,
                status_id__in=[
                    ReasoningStatusID.COMPLETED,
                    ReasoningStatusID.MAXED_OUT,
                    ReasoningStatusID.STOPPED,
                ],
            ).exists()

            if is_done:
                p.status_id = IterationShiftParticipantStatus.COMPLETED
                p.save(update_fields=['status'])
                logger.debug(
                    f'[TemporalLobe] Worker {p.id} verified finished. Marked COMPLETED.'
                )
            else:
                # They crashed or ghosted without completing. Demote them so the queue can grab them again!
                p.status_id = IterationShiftParticipantStatus.SELECTED
                p.save(update_fields=['status'])
                logger.debug(
                    f'[TemporalLobe] Ghost Worker {p.id} fully cleaned up and reverted to SELECTED.'
                )


def fetch_canonical_temporal_pathway():
    """Contained in initial_data.json fixture."""
    return NeuralPathway.objects.get(id='c3dd041a-20eb-4414-b571-2a5fdbeb9b86')


async def run_temporal_lobe(spike_id: str) -> Tuple[int, str]:
    """Engage the Temporal Lobe to process a spike."""
    lobe = TemporalLobe(spike_id)
    return await lobe.tick()


def trigger_temporal_metronomes() -> list:
    lobe_garbage_collection()
    # =========================================================================
    # STEP 2: SPAWN MISSING METRONOMES
    # =========================================================================
    active_iteration_environments = (
        Iteration.objects.filter(
            status_id__in=[IterationStatus.WAITING, IterationStatus.RUNNING]
        )
        .values_list('environment_id', flat=True)
        .distinct()
    )
    logger.debug(
        f'[TemporalLobe] Found {len(active_iteration_environments)} environments with iterations.'
    )
    if not active_iteration_environments:
        logger.debug(
            f'[TemporalLobe] No active iterations found, skipping metronome spawning.'
        )
        return []

    return get_or_create_environment_trains(active_iteration_environments)


def get_or_create_environment_trains(
    active_iteration_environments: list[UUID],
) -> list[UUID]:
    train_list = []
    pathway = fetch_canonical_temporal_pathway()
    for env_id in active_iteration_environments:
        # THE BOUNCER: Is there already a Metronome running for this project?
        # (It might have just been cleared by the ghost protocol above!)
        trains = SpikeTrain.objects.filter(
            pathway=pathway,
            environment_id=env_id,
            status_id__in=[SpikeTrainStatus.CREATED, SpikeTrainStatus.RUNNING],
        )
        is_already_running = trains.exists()
        if is_already_running:
            # TODO: Check that celery task is actually still running.
            logger.debug(
                f'[TemporalLobe] SpikeTrain for Environment {env_id} is already running.'
            )
            train_list.extend(trains.values_list('id', flat=True))

            continue

        # Safe to spawn!
        spike_train = SpikeTrain.objects.create(
            pathway=pathway,
            environment_id=env_id,
            status_id=SpikeTrainStatus.CREATED,
        )
        logger.debug(
            f'[TemporalLobe] Created new SpikeTrain {spike_train.id} for Environment {env_id}'
        )

        cns = CNS(spike_train_id=spike_train.id)
        logger.debug(
            f'[TemporalLobe] Starting CNS for SpikeTrain {spike_train.id}'
        )
        cns.start()

        train_list.append(spike_train.id)
        logger.debug(
            f'[TemporalLobe] Fired for Environment {env_id}: SpikeTrain {spike_train.id}'
        )

    return train_list


ZOMBIE_THRESHOLD_MINUTES = 20


def _is_spike_alive(spike: Spike) -> bool:
    if not spike.celery_task_id:
        return False

    task_id = str(spike.celery_task_id)
    zombie_cutoff = timezone.now() - timedelta(minutes=ZOMBIE_THRESHOLD_MINUTES)
    db_status = 'UNKNOWN'

    # ── 1. DEFINITIVE DEATH CHECKS (DB & Broker) ─────────────────────────────
    try:
        task_result = TaskResult.objects.get(task_id=task_id)
        db_status = task_result.status
        if db_status in states.READY_STATES:
            logger.debug(
                f'[TemporalLobe] DB confirms task {task_id} is dead ({db_status}).'
            )
            return False
    except TaskResult.DoesNotExist:
        db_status = 'PENDING'

    res = AsyncResult(task_id)
    if res.state in states.READY_STATES:
        logger.debug(
            f'[TemporalLobe] Broker confirms task {task_id} is dead ({res.state}).'
        )
        return False

    # ── 2. THE NUCLEAR OPTION (Worker Inspection) ────────────────────────────
    inspector_succeeded = False
    try:
        inspector = current_app.control.inspect()

        active_tasks = inspector.active()
        if active_tasks:
            inspector_succeeded = True
            for worker_name, tasks in active_tasks.items():
                if any(t['id'] == task_id for t in tasks):
                    logger.debug(
                        f'[TemporalLobe] Inspector caught {task_id} running on {worker_name}.'
                    )
                    return True

        reserved_tasks = inspector.reserved()
        if reserved_tasks:
            inspector_succeeded = True
            for worker_name, tasks in reserved_tasks.items():
                if any(t['id'] == task_id for t in tasks):
                    logger.debug(
                        f'[TemporalLobe] Inspector caught {task_id} reserved by {worker_name}.'
                    )
                    return True

    except Exception as e:
        logger.warning(
            f'[TemporalLobe] Celery Inspector failed for {task_id}: {e}'
        )

    # ── 3. IMMEDIATE GHOST EXECUTION ─────────────────────────────────────────
    # If the inspector successfully checked the workers, NO worker has the task,
    # BUT the database claims it is "STARTED", it is a confirmed Hard-Crash Ghost.
    if inspector_succeeded and db_status == 'STARTED':
        logger.warning(
            f'[TemporalLobe] DB says STARTED but workers are empty. Instant Ghost Kill: {task_id}'
        )
        return False

    # ── 4. THE QUEUE & PENDING HEURISTIC ─────────────────────────────────────
    # Task is PENDING. Give it 15 minutes to be picked up by a worker.
    if spike.created < zombie_cutoff:
        logger.warning(
            f'[TemporalLobe] Task {task_id} is unassigned and older than '
            f'{ZOMBIE_THRESHOLD_MINUTES} min. Timeout Ghost detected!'
        )
        return False

    logger.debug(
        f'[TemporalLobe] Task {task_id} is unassigned but new. '
        f"Assuming it's safely waiting in the queue."
    )
    return True


def lobe_garbage_collection() -> NeuralPathway:
    pathway = fetch_canonical_temporal_pathway()

    active_trains = SpikeTrain.objects.filter(
        pathway=pathway,
        status_id__in=[SpikeTrainStatus.CREATED, SpikeTrainStatus.RUNNING],
    )
    logger.debug(f'[TemporalLobe] Found {active_trains.count()} active trains.')

    for train in active_trains:
        logger.debug(f'[TemporalLobe] Processing metronome {train.id}.')

        active_spikes = train.spikes.filter(
            status_id__in=[SpikeStatus.RUNNING, SpikeStatus.PENDING]
        )
        logger.debug(
            f'[TemporalLobe] Found {active_spikes.count()} active spikes '
            f'for metronome {train.id}.'
        )

        # The train is alive if *any* of its spikes are genuinely running.
        train_is_alive = any(_is_spike_alive(spike) for spike in active_spikes)

        if train_is_alive:
            logger.debug(
                f'[TemporalLobe] SpikeTrain {train.id} has a pulse — leaving it alone.'
            )
            continue

        logger.warning(
            f'[TemporalLobe] Zombie detected: SpikeTrain {train.id} — triggering GC.'
        )
        try:
            CNS(spike_train_id=train.id).poll()
        except Exception as e:
            logger.error(
                f'[TemporalLobe] Error cleaning zombie SpikeTrain {train.id}: {e}',
                exc_info=True,
            )

    return pathway
