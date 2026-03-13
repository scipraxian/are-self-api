from common.tests.common_test_case import CommonFixturesAPITestCase
from identity.models import Identity, IdentityDisc
from temporal_lobe.models import (Shift, ShiftDefaultParticipant,
                                  IterationDefinition, IterationShiftDefinition,
                                  IterationStatus, Iteration, IterationShift,
                                  IterationShiftParticipantStatus,
                                  IterationShiftParticipant)


class TemporalLobeModelsTest(CommonFixturesAPITestCase):

    def test_iteration_shift_participant_relationships(self):
        # Create minimal objects required
        identity = Identity.objects.create(name="TempIdentity")
        # IdentityDisc now owns the identity fields directly; no FK to Identity.
        disc = IdentityDisc.objects.create(name="TempDisc")

        status = IterationStatus.objects.first()
        if not status:
            status = IterationStatus.objects.create(id=1, name="Waiting")

        definition = IterationDefinition.objects.create(name="TempDef")

        iteration = Iteration.objects.create(name="TestIterationModel",
                                             status=status,
                                             definition=definition)

        shift, _ = Shift.objects.get_or_create(id=1,
                                               defaults={'name': 'Grooming'})
        shift_def = IterationShiftDefinition.objects.create(
            definition=definition, shift=shift, order=1)

        iter_shift = IterationShift.objects.create(definition=shift_def,
                                                   shift_iteration=iteration,
                                                   shift=shift)

        participant = IterationShiftParticipant.objects.create(
            iteration_shift=iter_shift, iteration_participant=disc)

        self.assertEqual(str(iteration), "TestIterationModel")
        self.assertTrue(str(disc.name) in str(participant))
        self.assertTrue(str(shift.name) in str(iter_shift))
