import json
from random import random, randrange
from typing import Optional

from asgiref.sync import sync_to_async

from frontal_lobe.models import ReasoningTurn
from identity.addons.addon_package import AddonPackage
from identity.models import IdentityDisc, IdentityType
from prefrontal_cortex.models import PFCEpic, PFCItemStatus, PFCStory, PFCTask
from prefrontal_cortex.serializers import (
    PFCEpicDetailSerializer,
    PFCStoryDetailSerializer,
    PFCTaskDetailSerializer,
)
from temporal_lobe.models import Iteration, Shift


class AgilePromptBuilder:
    def __init__(self, package: AddonPackage):
        self.package = package
        self.iteration_id = None
        self.iteration_shift = None
        self.iteration = None
        self.identity_disc = None
        self.turn_number = None
        self.reasoning_turn = None
        self.context_lines = []
        self._extract_package()

    def _extract_package(self):
        self.iteration_id = self.package.iteration
        if not self.iteration_id:
            raise ValueError('No active iteration.')
        if self.package.identity_disc:
            self.identity_disc = IdentityDisc.objects.get(
                id=self.package.identity_disc
            )
        self.turn_number = self.package.turn_number
        if self.package.reasoning_turn_id is None:
            raise ValueError('No reasoning turn provided.')
        self.reasoning_turn = ReasoningTurn.objects.get(
            id=self.package.reasoning_turn_id
        )
        self.iteration_shift = (
            self.reasoning_turn.session.participant.iteration_shift
        )
        self.iteration = self.iteration_shift.shift_iteration
        self.shift = self.iteration_shift.shift

    def build_prompt(self) -> str:
        if not self.identity_disc:
            return '[AGILE BOARD CONTEXT: UI Preview Mode - No Active Disc Assigned]'
        self.context_lines = [
            '=========================================',
            f' AGILE BOARD CONTEXT | SHIFT: {self.shift.name}',
            '=========================================',
        ]

        id_type = self.identity_disc.identity.identity_type_id
        shift_id = self.shift.id

        # ---------------------------------------------------------
        # PM ROUTING
        # ---------------------------------------------------------
        if id_type == IdentityType.PM:
            if shift_id == Shift.GROOMING:
                self._handle_epic_grooming()
            elif shift_id in [Shift.PRE_PLANNING, Shift.PLANNING]:
                self._handle_story_planning()
            else:
                self.context_lines.append(
                    f"-> DIRECTIVE: Standby. No active PM directives for shift '{self.shift.name}'."
                )

        # ---------------------------------------------------------
        # WORKER ROUTING
        # ---------------------------------------------------------
        elif id_type == IdentityType.WORKER:
            if shift_id == Shift.EXECUTING:
                self._handle_task_execution()
            else:
                self.context_lines.append(
                    f"-> DIRECTIVE: Standby. No active Worker directives for shift '{self.shift.name}'."
                )

        return '\n'.join(self.context_lines)

    def _handle_epic_grooming(self):
        # Look for the exact Epic the PFC just locked to this disc
        epic = PFCEpic.objects.filter(owning_disc=self.identity_disc).first()
        if epic:
            # Serialize the ENTIRE nested object (Environment, Tags, Engrams, etc.)
            epic_data = PFCEpicDetailSerializer(epic).data
            self.context_lines.append(
                '-> DIRECTIVE: Groom this Epic. Break it down into strictly formatted Stories using mcp_ticket.'
            )
            self.context_lines.append('\n### ASSIGNED EPIC DATA ###')
            self.context_lines.append(json.dumps(epic_data, indent=2))
        else:
            self.context_lines.append(
                '-> DIRECTIVE: No Epic assigned. Review backlog or standby.'
            )

    def _handle_story_planning(self):
        # Look for the exact Story the PFC just locked to this disc
        story = PFCStory.objects.filter(owning_disc=self.identity_disc).first()
        if story:
            story_data = PFCStoryDetailSerializer(story).data
            self.context_lines.append(
                '-> DIRECTIVE: Verify DoR (Definition of Ready). Break this Story into actionable Tasks using mcp_ticket.'
            )
            self.context_lines.append('\n### ASSIGNED STORY DATA ###')
            self.context_lines.append(json.dumps(story_data, indent=2))
        else:
            self.context_lines.append(
                '-> DIRECTIVE: No Story assigned. Review backlog or standby.'
            )

    def _handle_task_execution(self):
        # Look for the exact Task the PFC just locked to this disc
        task = PFCTask.objects.filter(owning_disc=self.identity_disc).first()
        if task:
            task_data = PFCTaskDetailSerializer(task).data
            self.context_lines.append(
                '-> DIRECTIVE: Execute this task. Fulfill the parent story assertions. Document discoveries in Engrams. Close task when complete.'
            )
            self.context_lines.append('\n### ASSIGNED TASK DATA ###')
            self.context_lines.append(json.dumps(task_data, indent=2))
        else:
            self.context_lines.append(
                '-> DIRECTIVE: No Task assigned. Review backlog or standby.'
            )


# Keep the async wrapper exactly as you had it
async def agile_addon(package: AddonPackage) -> str:
    """
    Identity Addon: Dynamically injects the active Agile Board context into the system prompt.
    Adapts the ticket payload based on the current Temporal Shift (Grooming, Planning, Executing).
    """
    # Using sync_to_async to wrap the DB calls inside the builder
    builder = AgilePromptBuilder(package)
    return await sync_to_async(builder.build_prompt)()
