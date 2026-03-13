import logging
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from identity.models import IdentityDisc
from temporal_lobe.models import (
    Iteration,
    IterationDefinition,
    IterationShift,
    IterationShiftParticipant,
    IterationStatus,
)

logger = logging.getLogger(__name__)


class IterationInceptionManager:
    """
    The Biological Engine responsible for translating an Iteration Blueprint
    into a living, stateful runtime execution track.
    """

    @classmethod
    @transaction.atomic
    def incept_iteration(
        cls,
        definition_id: int,
        environment_id: UUID = None,
        custom_name: str = None,
    ) -> Iteration:
        # 1. Fetch the Blueprint
        definition = IterationDefinition.objects.prefetch_related(
            'iterationshiftdefinition_set__iterationshiftdefinitionparticipant_set__identity_disc'
        ).get(id=definition_id)

        # Ensure we have the "Waiting" status ready (ID 1 from your fixtures)
        status_waiting, _ = IterationStatus.objects.get_or_create(
            id=1, defaults={'name': 'Waiting'}
        )

        # 2. Incept the base Iteration
        iteration_name = (
            custom_name
            or f'{definition.name} - {timezone.now().strftime("%Y-%m-%d %H:%M")}'
        )

        iteration = Iteration.objects.create(
            name=iteration_name,
            definition=definition,
            status=status_waiting,
            environment_id=environment_id,
        )

        first_shift = None

        # 3. Sequence the Shifts
        shift_defs = definition.iterationshiftdefinition_set.all().order_by(
            'order'
        )
        for s_def in shift_defs:
            new_shift = IterationShift.objects.create(
                shift_iteration=iteration, definition=s_def, shift=s_def.shift
            )

            if not first_shift:
                first_shift = new_shift

            # 4. Staffing: Attach the configured Discs for this shift definition
            participants = s_def.iterationshiftdefinitionparticipant_set.all()
            for p_def in participants:
                identity_disc = p_def.identity_disc

                # Bind the Disc to the Shift's Synapses
                IterationShiftParticipant.objects.create(
                    iteration_shift=new_shift,
                    iteration_participant=identity_disc,
                )

        # 5. Set the starting point
        if first_shift:
            iteration.current_shift = first_shift
            iteration.save(update_fields=['current_shift'])

        return iteration

    @classmethod
    def gestate_disc(cls, base_identity) -> IdentityDisc:
        """
        Gestation: The biological process of growing a stateful
        Identity Disc from a Base Identity template.
        """
        # Give the clone a unique lineage designation (e.g., "Worker [Mk.3]")
        count = IdentityDisc.objects.filter(identity=base_identity).count() + 1
        new_name = f'{base_identity.name} [Mk.{count}]'

        new_disc = IdentityDisc.objects.create(
            name=new_name,
            identity=base_identity,
            level=1,
            xp=0,
            available=False,  # Spawned directly into a deployment
            successes=0,
            failures=0,
            timeouts=0,
        )
        return new_disc
