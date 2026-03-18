from frontal_lobe.models import ReasoningTurn
from identity.addons.addon_package import AddonPackage


def identity_info_addon(package: AddonPackage) -> str:
    iteration_id = None
    if self.session.participant_id:
        from temporal_lobe.models import IterationShiftParticipant

        try:
            p = IterationShiftParticipant.objects.select_related(
                'iteration_shift'
            ).get(id=self.session.participant_id)
            iteration_id = p.iteration_shift.shift_iteration_id
        except IterationShiftParticipant.DoesNotExist:
            pass

    return build_identity_prompt(
        identity_disc=self.session.identity_disc,
        iteration_id=iteration_id,
        turn_number=turn_record.turn_number,
        reasoning_turn_id=turn_record.id,
    )
