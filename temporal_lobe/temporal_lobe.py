import logging

from temporal_lobe.models import (
    Iteration,
    IterationShiftParticipantStatus,
    IterationStatus,
)

logger = logging.getLogger(__name__)


class TemporalLobe:
    """The pure state machine for managing Time and Workers."""

    @classmethod
    def initiate_iteration(cls, iteration: Iteration):
        """The Ignition Switch."""
        if not iteration.current_shift:
            first_shift = iteration.iterationshift_set.order_by(
                'definition__order'
            ).first()
            if not first_shift:
                logger.error(
                    f'Cannot initiate Iteration {iteration.id}: No shifts exist.'
                )
                return
            iteration.current_shift = first_shift

        status_running, _ = IterationStatus.objects.get_or_create(
            id=IterationStatus.RUNNING, defaults={'name': 'Running'}
        )
        iteration.status = status_running
        iteration.save(update_fields=['status', 'current_shift'])

        logger.info(
            f'[TemporalLobe] Iteration {iteration.id} initiated. Evaluating board...'
        )
        cls.evaluate_and_advance(iteration)

    @classmethod
    def evaluate_and_advance(cls, iteration: Iteration):
        shift = iteration.current_shift
        if not shift:
            return

        # 1. Is someone already activated? Wait for them.
        active_participant = shift.iterationshiftparticipant_set.filter(
            status_id=IterationShiftParticipantStatus.ACTIVATED
        ).first()

        if active_participant:
            logger.info(
                f'[TemporalLobe] Waiting on {active_participant.iteration_participant.name}.'
            )
            return

        # 2. Find the next SELECTED worker
        next_participant = (
            shift.iterationshiftparticipant_set.filter(
                status_id=IterationShiftParticipantStatus.SELECTED
            )
            .order_by('id')
            .first()
        )

        if next_participant:
            # Transition to ACTIVATED
            next_participant.status_id = (
                IterationShiftParticipantStatus.ACTIVATED
            )
            next_participant.save(update_fields=['status'])

            logger.info(
                f'[TemporalLobe] Dispatching {next_participant.iteration_participant.name} to PFC.'
            )

            # Hand off to the boundary layer
            from prefrontal_cortex.prefrontal_cortex import PrefrontalCortex

            PrefrontalCortex.dispatch_worker(next_participant)
        else:
            # 3. Check if all workers in this shift are COMPLETED
            uncompleted = shift.iterationshiftparticipant_set.exclude(
                status_id=IterationShiftParticipantStatus.COMPLETED
            ).exists()

            if not uncompleted:
                logger.info(
                    f"[TemporalLobe] Shift '{shift.name}' complete. Advancing."
                )
                next_shift = (
                    iteration.iterationshift_set.filter(
                        definition__order__gt=shift.definition.order
                    )
                    .order_by('definition__order')
                    .first()
                )

                if next_shift:
                    iteration.current_shift = next_shift
                    iteration.save(update_fields=['current_shift'])
                    cls.evaluate_and_advance(iteration)
                else:
                    logger.info(
                        f'[TemporalLobe] Iteration {iteration.id} complete.'
                    )
                    status_finished, _ = IterationStatus.objects.get_or_create(
                        id=IterationStatus.FINISHED,
                        defaults={'name': 'Finished'},
                    )
                    iteration.status = status_finished
                    iteration.current_shift = None
                    iteration.save(update_fields=['status', 'current_shift'])

                    # Release Discs back to the Barracks
                    from identity.models import IdentityDisc

                    participants = iteration.iterationshift_set.values_list(
                        'iterationshiftparticipant_set__iteration_participant',
                        flat=True,
                    )
                    IdentityDisc.objects.filter(
                        id__in=[p for p in participants if p]
                    ).update(available=True)
