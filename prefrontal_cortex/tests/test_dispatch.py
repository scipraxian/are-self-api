import uuid
from unittest.mock import AsyncMock, patch

import pytest
from asgiref.sync import sync_to_async

from central_nervous_system.models import (
    NeuralPathway,
    Spike,
    SpikeStatus,
    SpikeTrain,
    SpikeTrainStatus,
)
from common.tests.common_test_case import CommonFixturesAPITestCase
from identity.models import Identity, IdentityDisc, IdentityType
from prefrontal_cortex.models import PFCEpic, PFCItemStatus
from prefrontal_cortex.prefrontal_cortex import PrefrontalCortex
from temporal_lobe.models import (
    Iteration,
    IterationDefinition,
    IterationShift,
    IterationShiftDefinition,
    IterationShiftParticipant,
    IterationStatus,
    Shift,
)


class PrefrontalCortexDispatchTest(CommonFixturesAPITestCase):
    def setUp(self):
        # 1. Base Setup
        self.pathway = NeuralPathway.objects.create(name='Test Pathway')
        self.spike_train = SpikeTrain.objects.create(
            pathway=self.pathway, status_id=SpikeTrainStatus.RUNNING
        )
        self.spike = Spike.objects.create(
            spike_train=self.spike_train, status_id=SpikeStatus.RUNNING
        )

        # 2. Agile Setup
        self.status_backlog = PFCItemStatus.objects.get(
            id=PFCItemStatus.BACKLOG
        )
        self.status_done = PFCItemStatus.objects.get(id=PFCItemStatus.DONE)

        # 3. Temporal Setup
        self.shift_sifting = Shift.objects.get(id=Shift.SIFTING)
        self.iteration_def = IterationDefinition.objects.first()

        # FIX: Get the existing shift definition from the fixture to prevent IntegrityError
        self.shift_def = IterationShiftDefinition.objects.get(
            definition=self.iteration_def, shift=self.shift_sifting, order=1
        )

        self.iteration = Iteration.objects.create(
            status_id=IterationStatus.RUNNING, definition=self.iteration_def
        )
        self.iter_shift = IterationShift.objects.create(
            shift_iteration=self.iteration,
            definition=self.shift_def,
            shift=self.shift_sifting,
        )

        # 4. Identity Setup (PM)
        pm_type = IdentityType.objects.get(name='PM')
        self.identity = Identity.objects.create(
            name='Test PM', identity_type=pm_type
        )
        self.disc = IdentityDisc.objects.create(
            name='Test PM Disc', identity=self.identity
        )

        self.participant = IterationShiftParticipant.objects.create(
            iteration_shift=self.iter_shift, iteration_participant=self.disc
        )

    @pytest.mark.asyncio
    async def test_dispatch_bounces_when_no_work(self):
        """Verify the PFC refuses to spin up a Frontal Lobe if the backlog is empty."""
        pfc = PrefrontalCortex(self.spike.id)

        # ACT: Dispatch with NO Epics in the database
        session_id = await pfc.dispatch(
            self.participant.id, environment_id=None
        )

        # ASSERT: The bouncer caught it
        self.assertIsNone(session_id)
