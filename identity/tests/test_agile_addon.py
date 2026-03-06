import json
import os
import pytest
from asgiref.sync import sync_to_async
from django.test import TransactionTestCase

from identity.models import Identity, IdentityDisc, IdentityType

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
from temporal_lobe.models import (Iteration, IterationDefinition,
                                  IterationShift, Shift,
                                  IterationShiftParticipant, IterationStatus,
                                  IterationShiftDefinition)
from prefrontal_cortex.models import PFCEpic, PFCItemStatus
from frontal_lobe.models import ReasoningSession, ReasoningTurn
from identity.addons.addon_package import AddonPackage
from identity.addons.agile_addon import agile_addon


class AgileAddonTest(TransactionTestCase):
    fixtures = [
        'environments/fixtures/initial_data.json',
        'peripheral_nervous_system/fixtures/initial_data.json',
        'peripheral_nervous_system/fixtures/test_agents.json',
        'central_nervous_system/fixtures/initial_data.json',
        'frontal_lobe/fixtures/initial_data.json',
        'identity/fixtures/initial_data.json',
        'parietal_lobe/fixtures/initial_data.json',
        'prefrontal_cortex/fixtures/initial_data.json',
        'temporal_lobe/fixtures/initial_data.json',
    ]

    @pytest.mark.asyncio
    async def test_agile_addon_prompt_generation(self):
        # 1. Setup Statuses & Types
        worker_type, _ = await sync_to_async(IdentityType.objects.get_or_create
                                            )(id=IdentityType.WORKER,
                                              defaults={
                                                  'name': 'Worker'
                                              })
        pm_type, _ = await sync_to_async(IdentityType.objects.get_or_create
                                        )(id=IdentityType.PM,
                                          defaults={
                                              'name': 'PM'
                                          })

        iteration_status, _ = await sync_to_async(
            IterationStatus.objects.get_or_create)(id=IterationStatus.RUNNING,
                                                   defaults={
                                                       'name': 'Running'
                                                   })
        pfc_status, _ = await sync_to_async(PFCItemStatus.objects.get_or_create
                                           )(id=PFCItemStatus.BACKLOG,
                                             defaults={
                                                 'name': 'Backlog'
                                             })

        grooming_shift, _ = await sync_to_async(Shift.objects.get_or_create
                                               )(id=Shift.GROOMING,
                                                 defaults={
                                                     'name': 'Grooming'
                                                 })

        # 2. Setup Identities
        pm_identity = await sync_to_async(Identity.objects.create
                                         )(name="Test PM",
                                           identity_type=pm_type,
                                           system_prompt_template="PM prompt")
        pm_disc = await sync_to_async(IdentityDisc.objects.create
                                     )(identity=pm_identity, name="PM Disc 1")

        # 3. Setup Iteration & Sessions
        iter_def = await sync_to_async(IterationDefinition.objects.create
                                      )(name="Test Iteration Def")
        iteration = await sync_to_async(Iteration.objects.create
                                       )(name="Test Iteration",
                                         status=iteration_status,
                                         definition=iter_def)

        iter_shift_def_groom = await sync_to_async(
            IterationShiftDefinition.objects.create)(definition=iter_def,
                                                     shift=grooming_shift,
                                                     order=1)

        iteration_shift_groom = await sync_to_async(
            IterationShift.objects.create)(definition=iter_shift_def_groom,
                                           shift_iteration=iteration,
                                           shift=grooming_shift)

        pm_participant = await sync_to_async(
            IterationShiftParticipant.objects.create
        )(iteration_shift=iteration_shift_groom, iteration_participant=pm_disc)

        pm_session = await sync_to_async(ReasoningSession.objects.create
                                        )(identity_disc=pm_disc,
                                          participant=pm_participant)

        pm_turn = await sync_to_async(ReasoningTurn.objects.create
                                     )(session=pm_session,
                                       turn_number=1,
                                       thought_process="Planning...")

        # 4. Setup Epic
        epic = await sync_to_async(PFCEpic.objects.create
                                  )(name="Super Epic Test",
                                    owning_disc=pm_disc,
                                    status=pfc_status,
                                    perspective="User perspective",
                                    assertions="Assert something")

        # 5. Build AddonPackage and Invoke
        pm_package = AddonPackage(iteration=iteration.id,
                                  identity=pm_identity.id,
                                  identity_disc=pm_disc.id,
                                  turn_number=1,
                                  reasoning_turn_id=pm_turn.id)

        pm_prompt = await agile_addon(pm_package)

        # 6. Assertions
        assert "Super Epic Test" in pm_prompt
        assert "Groom this Epic" in pm_prompt
        assert "AGILE BOARD CONTEXT" in pm_prompt
