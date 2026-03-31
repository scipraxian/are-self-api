import json
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from frontal_lobe.models import ReasoningTurn
from identity.models import IdentityDisc, IdentityType
from prefrontal_cortex.models import PFCEpic, PFCItemStatus, PFCStory, PFCTask
from prefrontal_cortex.serializers import (
    PFCEpicSerializer,
    PFCStorySerializer,
    PFCTaskSerializer,
)
from temporal_lobe.models import Shift

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MCP_TOOL_MECHANICS = """\
--- TOOL MECHANICS ---
Use `mcp_ticket` with the following interface:
  mcp_ticket(action, item_type?, item_id?, field_name?, field_value?, parent_id?, body?)

Actions:
  'create'  — Creates a new ticket. Requires: item_type, parent_id.
  'read'    — Reads a ticket. Requires: item_id.
  'update'  — Updates a single field. Requires: item_id, field_name, field_value.
              One call per field. To update two fields, call twice.
  'comment' — Adds a comment. Requires: item_id, body.

Valid status values for field_name='status':
  1=NEEDS_REFINEMENT  2=BACKLOG            3=SELECTED_FOR_DEV
  4=IN_PROGRESS       5=IN_REVIEW          6=BLOCKED_BY_USER   7=DONE

Valid item_type values: 'EPIC', 'STORY', 'TASK'
"""

_NO_ASSIGNMENT_MESSAGE = (
    '[AGILE BOARD] You have no active assignments for this shift. '
    'Proceed to consolidate memories.'
)

# ---------------------------------------------------------------------------
# Ticket resolution
# ---------------------------------------------------------------------------

_TICKET_TYPES = [
    ('EPIC', PFCEpic, PFCEpicSerializer),
    ('STORY', PFCStory, PFCStorySerializer),
    ('TASK', PFCTask, PFCTaskSerializer),
]


def _get_locked_ticket(
    identity_disc_id: UUID,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Return (item_type, item_id, item_json) for the single ticket locked to
    this disc, or (None, None, None) if none exists.
    """
    for item_type, model, serializer in _TICKET_TYPES:
        instance = model.objects.filter(owning_disc_id=identity_disc_id).first()
        if instance:
            item_json = json.dumps(serializer(instance).data, default=str)
            return item_type, str(instance.id), item_json

    return None, None, None


# ---------------------------------------------------------------------------
# PM instruction builders
# ---------------------------------------------------------------------------


def _pm_instructions_sifting(
    shift_id: int, item_type: str, item_id: str
) -> str:
    return f"""\
ROLE: Sifting Project Manager
GOAL: Refine this {item_type} until it meets the Definition of Ready (DoR).

DEFINITION OF READY — EVERY single one of these fields MUST have comprehensive text:
  1. perspective    — The 'why' (business value) and 'who' (affected users/teams).
  2. assertions     — Bulleted, independently testable completion criteria.
  3. outside        — Explicit scope exclusions (what NOT to do).
  4. dod_exceptions — Any agreed deviations from the standard Definition of Done.
  5. dependencies   — IDs of tickets that must be resolved first.
  6. demo_specifics — Who will witness the demo and exactly what will be shown.

CRITICAL INSTRUCTIONS:
  - You MUST make a separate `mcp_ticket(action='update')` call for EVERY empty field.
  - DO NOT change the status to BACKLOG until you have written out the 'perspective' and 'assertions' at a minimum. 
  - If you change the status without filling out the DoR, the system will reject your update.
"""


def _pm_instructions_pre_planning(
    shift_id: int, item_type: str, item_id: str
) -> str:
    return f"""\
ROLE: Pre-Planning Project Manager
GOAL: Review this {item_type} and route it correctly.

IF IT IS AN EPIC IN BACKLOG (status=2):
  Move to BLOCKED_BY_USER (status=6) so a human can approve the budget.

IF IT IS AN EPIC IN SELECTED_FOR_DEV (status=3):
  The budget is approved! Decompose this Epic into discrete child STORY tickets using:
  mcp_ticket(action='create', item_type='STORY', parent_id='{item_id}')

IF IT IS A STORY:
  Move to SELECTED_FOR_DEV (status=3) so workers can begin.
"""


def _pm_instructions_post_execution(
    shift_id: int, item_type: str, item_id: str
) -> str:
    return f"""\
ROLE: Post-Execution QA Manager
GOAL: Determine whether this {item_type} satisfies the Definition of Done (DoD).

PASS → Every assertion in the ticket is verifiably met.
       Move to BLOCKED_BY_USER (status=6) for final human sign-off.

FAIL → At least one assertion is unmet or the work is flawed.
       Leave a specific comment explaining the failure.
       Move back to SELECTED_FOR_DEV (status=3).
"""


_PM_INSTRUCTION_BUILDERS = {
    Shift.SIFTING: _pm_instructions_sifting,
    Shift.PRE_PLANNING: _pm_instructions_pre_planning,
    Shift.POST_EXECUTION: _pm_instructions_post_execution,
}


def _build_pm_instructions(shift_id: int, item_type: str, item_id: str) -> str:
    # 1. Get the builder function using ONLY the key (shift_id)
    builder = _PM_INSTRUCTION_BUILDERS.get(shift_id)

    if builder:
        # 2. Call the builder function with the three arguments it requires
        return builder(shift_id, item_type, item_id)

    return 'You have no actionable tickets for this shift. Sleep and consolidate your memories.'


# ---------------------------------------------------------------------------
# Worker instruction builders
# ---------------------------------------------------------------------------


def _worker_instructions_sifting(item_type: str, item_id: str) -> str:
    return f"""\
ROLE: Estimating Worker
GOAL: Provide a complexity BID for this {item_type}.

COMPLEXITY SCALE (number of AI turns expected to complete the ticket):
  1–2   Very small — a single self-contained change.
  3–5   Small — a few related changes.
  6–10  Medium — multiple components or integration work.
  11+   Large — consider asking a PM to split the ticket.

SUCCESS: Update the complexity field with your integer estimate:
  mcp_ticket(action='update', item_id='{item_id}', field_name='complexity', field_value='<integer>')
  Do NOT use descriptive text — the value must be a raw integer (e.g., "4").
"""


def _worker_instructions_pre_planning(item_type: str, item_id: str) -> str:
    return f"""\
ROLE: Architectural Worker
GOAL: Decompose this {item_type} into discrete, executable TASKs.

STEPS:
  1. Read the 'assertions' field carefully — each assertion maps to ≥1 task.
  2. For each distinct technical step, create a child TASK:
       mcp_ticket(action='create', item_type='TASK', parent_id='{item_id}')
  3. Keep tasks isolated and strictly technical (no UI copy, no PM work).

WARNING: You will execute every task you create. Do not over-decompose.
SUCCESS:  All tasks created → your shift is complete.
"""


def _worker_instructions_executing(item_type: str, item_id: str) -> str:
    return f"""\
ROLE: Executing Developer
GOAL: Complete all code/work required for this {item_type}.

STEPS:
  1. Set status to IN_PROGRESS:
       mcp_ticket(action='update', item_id='{item_id}', field_name='status', field_value='4')
  2. Implement the work described in the 'assertions' field using your system tools.
  3. When fully complete, set status to IN_REVIEW:
       mcp_ticket(action='update', item_id='{item_id}', field_name='status', field_value='5')
"""


def _worker_instructions_post_execution(item_type: str, item_id: str) -> str:
    return f"""\
ROLE: Peer Review Worker
GOAL: Verify that the submitted work for this {item_type} satisfies every assertion.

PASS → All assertions met:
       mcp_ticket(action='update', item_id='{item_id}', field_name='status', field_value='7')  # DONE

FAIL → At least one assertion unmet:
       1. Leave a detailed comment explaining what failed and why.
       2. mcp_ticket(action='update', item_id='{item_id}', field_name='status', field_value='3')  # Back to SELECTED_FOR_DEV
"""


_WORKER_INSTRUCTION_BUILDERS = {
    Shift.SIFTING: _worker_instructions_sifting,
    Shift.PRE_PLANNING: _worker_instructions_pre_planning,
    Shift.EXECUTING: _worker_instructions_executing,
    Shift.POST_EXECUTION: _worker_instructions_post_execution,
}


def _build_worker_instructions(
    shift_id: int, item_type: str, item_id: str
) -> str:
    builder = _WORKER_INSTRUCTION_BUILDERS.get(shift_id)
    if builder:
        return builder(item_type, item_id)
    return 'You have no actionable tickets for this shift. Sleep and consolidate your memories.'


# ---------------------------------------------------------------------------
# Content assembly
# ---------------------------------------------------------------------------


def _build_assignment_content(
    shift_id: int,
    item_type: str,
    item_id: str,
    item_json: str,
    is_pm: bool,
) -> str:
    role_label = 'PM' if is_pm else 'WORKER'
    instructions = (
        _build_pm_instructions(shift_id, item_type, item_id)
        if is_pm
        else _build_worker_instructions(shift_id, item_type, item_id)
    )

    return (
        f'{"=" * 57}\n'
        f' AGILE SHIFT ASSIGNMENT | {role_label} | TICKET: {item_id}\n'
        f'{"=" * 57}\n'
        f'{instructions}\n'
        f'{_MCP_TOOL_MECHANICS}\n'
        f'--- ASSIGNED TICKET DATA ---\n'
        f'{item_json}'
    )


# ---------------------------------------------------------------------------
# Public addon entry point
# ---------------------------------------------------------------------------


def agile_addon(turn: ReasoningTurn) -> List[Dict[str, Any]]:
    """
    Identity Addon (Phase: CONTEXT)

    Resolves the ticket locked to this AI disc and injects hyper-focused
    shift instructions as a volatile USER message.
    """
    if (
        not turn
        or not turn.session.participant
        or not turn.session.identity_disc
    ):
        return []

    participant = turn.session.participant
    shift_id = participant.iteration_shift.shift_id
    disc = turn.session.identity_disc

    item_type, item_id, item_json = _get_locked_ticket(disc.id)

    if item_type is None:
        content = _NO_ASSIGNMENT_MESSAGE
    else:
        content = _build_assignment_content(
            shift_id=shift_id,
            item_type=item_type,
            item_id=item_id,
            item_json=item_json,
            is_pm=(disc.identity_type_id == IdentityType.PM),
        )

    return [{'role': 'system', 'content': content}]
