import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from asgiref.sync import sync_to_async
from django.core.exceptions import ObjectDoesNotExist

from frontal_lobe.models import ReasoningSession
from prefrontal_cortex.models import (
    PFCComment,
    PFCEpic,
    PFCItemStatus,
    PFCStory,
    PFCTask,
)

logger = logging.getLogger(__name__)


class TicketConstants:
    """Centralized string literals for Agile Board operations."""

    # Actions
    ACTION_CREATE = 'CREATE'
    ACTION_READ = 'READ'
    ACTION_UPDATE = 'UPDATE'
    ACTION_COMMENT = 'COMMENT'
    VALID_ACTIONS = [ACTION_CREATE, ACTION_READ, ACTION_UPDATE, ACTION_COMMENT]

    # Item Types
    TYPE_EPIC = 'EPIC'
    TYPE_STORY = 'STORY'
    TYPE_TASK = 'TASK'
    VALID_TYPES = [TYPE_EPIC, TYPE_STORY, TYPE_TASK]

    # Statuses
    STATUS_BACKLOG = 'BACKLOG'
    STATUS_SELECTED = 'SELECTED_FOR_DEVELOPMENT'
    STATUS_IN_PROGRESS = 'IN_PROGRESS'
    STATUS_BLOCKED = 'BLOCKED_BY_USER'

    # Personas
    PERSONA_ORACLE = 'ORACLE'
    PERSONA_AUTOMATON = 'AUTOMATON'

    # Error Messages
    ERR_INVALID_ACTION = "Error: Invalid action '{action}'. Must be CREATE, READ, UPDATE, or COMMENT."
    ERR_INVALID_TYPE = (
        "Error: Invalid item_type '{item_type}'. Must be EPIC, STORY, or TASK."
    )
    ERR_PAO = 'ERROR: Story rejected. Experience Master methodology requires Perspective, Assertions, and Outside clauses. Try again.'
    ERR_DOR_DEMO = 'ERROR: Cannot promote Story to SELECTED_FOR_DEVELOPMENT. It fails the Definition of Ready (DoR) because Demo Specifics are missing.'
    ERR_DOR_DEPS = 'ERROR: Cannot promote Story to SELECTED_FOR_DEVELOPMENT. It fails the Definition of Ready (DoR) because Dependencies are missing.'
    ERR_COMPLEXITY = 'ERROR: PMs cannot bid complexity. Only the Worker can bid complexity during the Planning Phase.'
    ERR_MISSING_ID = "Error: 'item_id' is required to {action} a {item_type}."
    ERR_MISSING_NAME = "Error: 'name' is required for CREATE action."
    ERR_MISSING_PARENT_STORY = (
        "Error: 'parent_id' (Epic UUID) is required to create a STORY."
    )
    ERR_MISSING_PARENT_TASK = (
        "Error: 'parent_id' (Story UUID) is required to create a TASK."
    )
    ERR_MISSING_TEXT = "Error: 'text' is required for COMMENT action."


@dataclass
class TicketYield:
    """Strictly typed yield for the Parietal Lobe to consume."""

    message: str
    focus_yield: int = 0
    xp_yield: int = 0

    def __str__(self):
        return self.message


# --- VALIDATION BOUNCERS ---


def _validate_pao(
    item_type: str, action: str, effective_state: Dict[str, Any]
) -> Optional[str]:
    """Rule 1: The PAO Enforcer."""
    if item_type != TicketConstants.TYPE_STORY:
        return None
    if action not in [
        TicketConstants.ACTION_CREATE,
        TicketConstants.ACTION_UPDATE,
    ]:
        return None

    has_p = bool((effective_state.get('perspective') or '').strip())
    has_a = bool((effective_state.get('assertions') or '').strip())
    has_o = bool((effective_state.get('outside') or '').strip())

    if not (has_p and has_a and has_o):
        return TicketConstants.ERR_PAO
    return None


def _validate_dor(
    item_type: str, effective_state: Dict[str, Any]
) -> Optional[str]:
    """Rule 2: The Pre-Planning Gatekeeper."""
    if item_type != TicketConstants.TYPE_STORY:
        return None

    status_name = effective_state.get('status') or ''
    if status_name != TicketConstants.STATUS_SELECTED:
        return None

    has_deps = bool((effective_state.get('dependencies') or '').strip())
    has_demo = bool((effective_state.get('demo_specifics') or '').strip())

    if not has_demo:
        return TicketConstants.ERR_DOR_DEMO
    if not has_deps:
        return TicketConstants.ERR_DOR_DEPS

    return None


def _validate_complexity(
    complexity: Optional[int], session_id: Optional[str]
) -> Optional[str]:
    """Rule 3: The Complexity Bid Shield."""
    if complexity is None or not session_id:
        return None

    try:
        session = ReasoningSession.objects.select_related('spike').get(
            id=session_id
        )
        # TODO: NO we check for addons here.
        if session.spike and session.spike.blackboard:
            persona = session.spike.blackboard.get('persona', '')
            if persona.upper() == TicketConstants.PERSONA_ORACLE:
                return TicketConstants.ERR_COMPLEXITY
    except ReasoningSession.DoesNotExist:
        pass

    return None


# --- ACTION HANDLERS ---


def _resolve_status_obj(status_str: Optional[str]) -> Optional[PFCItemStatus]:
    """Safely resolves a status string to a database object."""
    if not status_str:
        return None
    status_clean = status_str.replace('_', ' ')
    try:
        return PFCItemStatus.objects.get(name__iexact=status_clean)
    except PFCItemStatus.DoesNotExist:
        logger.warning(
            f"Status '{status_str}' not found. Falling back to Backlog."
        )
        return PFCItemStatus.objects.get(id=PFCItemStatus.BACKLOG)


def _handle_read(
    model_class, item_type: str, item_id: Optional[str]
) -> TicketYield:
    if not item_id:
        return TicketYield(
            TicketConstants.ERR_MISSING_ID.format(
                action='READ', item_type=item_type
            )
        )

    obj = model_class.objects.get(id=item_id)
    res = [f'--- {item_type}: {obj.name} [{obj.status.name}] ---']

    if getattr(obj, 'description', None):
        res.append(f'Description:\n{obj.description}\n')
    if getattr(obj, 'perspective', None):
        res.append(f'Perspective:\n{obj.perspective}\n')
    if getattr(obj, 'assertions', None):
        res.append(f'Assertions:\n{obj.assertions}\n')
    if getattr(obj, 'outside', None):
        res.append(f'Outside Bounds:\n{obj.outside}\n')
    if getattr(obj, 'dependencies', None):
        res.append(f'Dependencies:\n{obj.dependencies}\n')

    comments = []
    if item_type == TicketConstants.TYPE_EPIC:
        comments = obj.comments.all().order_by('created')
        children = obj.stories.all()
        if children.exists():
            res.append('Child Stories:')
            for c in children:
                res.append(f'- {c.id} | {c.name} [{c.status.name}]')
    elif item_type == TicketConstants.TYPE_STORY:
        comments = obj.comments.all().order_by('created')
        children = obj.tasks.all()
        if children.exists():
            res.append('\nChild Tasks:')
            for c in children:
                res.append(f'- {c.id} | {c.name} [{c.status.name}]')
    elif item_type == TicketConstants.TYPE_TASK:
        comments = obj.comments.all().order_by('created')

    if comments:
        res.append('\nComments:')
        for c in comments:
            author = c.user.username if c.user else 'Are-Self'
            res.append(
                f'[{c.created.strftime("%Y-%m-%d %H:%M")}] {author}: {c.text}'
            )

    return TicketYield('\n'.join(res))


def _handle_create(
    model_class, item_type: str, payload: Dict[str, Any]
) -> TicketYield:
    name = payload.get('name')
    parent_id = payload.get('parent_id')

    if not name:
        return TicketYield(TicketConstants.ERR_MISSING_NAME)

    kwargs = {'name': name}
    status_obj = _resolve_status_obj(payload.get('status'))
    if status_obj:
        kwargs['status'] = status_obj

    if item_type == TicketConstants.TYPE_STORY:
        if not parent_id:
            return TicketYield(TicketConstants.ERR_MISSING_PARENT_STORY)
        kwargs['epic'] = PFCEpic.objects.get(id=parent_id)
    elif item_type == TicketConstants.TYPE_TASK:
        if not parent_id:
            return TicketYield(TicketConstants.ERR_MISSING_PARENT_TASK)
        kwargs['story'] = PFCStory.objects.get(id=parent_id)

    # FIX: Check hasattr(model_class) to prevent AI from injecting Story fields into Tasks
    for field in [
        'description',
        'perspective',
        'assertions',
        'outside',
        'dod_exceptions',
        'dependencies',
        'demo_specifics',
        'priority',
    ]:
        if payload.get(field) is not None and hasattr(model_class, field):
            kwargs[field] = payload.get(field)

    if payload.get('complexity') is not None and hasattr(
        model_class, 'complexity'
    ):
        kwargs['complexity'] = payload.get('complexity')

    obj = model_class.objects.create(**kwargs)
    return TicketYield(
        f"Success: Created {item_type} '{obj.name}' with ID: {obj.id}"
    )


def _handle_update(
    model_class, item_type: str, item_id: Optional[str], payload: Dict[str, Any]
) -> TicketYield:
    if not item_id:
        return TicketYield(
            TicketConstants.ERR_MISSING_ID.format(
                action='UPDATE', item_type=item_type
            )
        )

    obj = model_class.objects.get(id=item_id)

    if payload.get('name') is not None:
        obj.name = payload.get('name')

    status_obj = _resolve_status_obj(payload.get('status'))
    if status_obj:
        obj.status = status_obj

    # FIX: Safely check hasattr(obj)
    for field in [
        'description',
        'perspective',
        'assertions',
        'outside',
        'dod_exceptions',
        'dependencies',
        'demo_specifics',
        'priority',
    ]:
        if payload.get(field) is not None and hasattr(obj, field):
            setattr(obj, field, payload.get(field))

    if payload.get('complexity') is not None and hasattr(obj, 'complexity'):
        obj.complexity = payload.get('complexity')

    obj.save()
    return TicketYield(f'Success: Updated {item_type} {obj.id}.')


def _handle_comment(
    model_class, item_type: str, item_id: Optional[str], text: Optional[str]
) -> TicketYield:
    if not item_id:
        return TicketYield(
            TicketConstants.ERR_MISSING_ID.format(
                action='COMMENT', item_type=item_type
            )
        )
    if not text:
        return TicketYield(TicketConstants.ERR_MISSING_TEXT)

    obj = model_class.objects.get(id=item_id)
    kwargs = {'text': text}

    if item_type == TicketConstants.TYPE_EPIC:
        kwargs['epic'] = obj
    elif item_type == TicketConstants.TYPE_STORY:
        kwargs['story'] = obj
    elif item_type == TicketConstants.TYPE_TASK:
        kwargs['task'] = obj

    PFCComment.objects.create(**kwargs)

    # Rule 4: The Breadcrumb Router (Synthesis Action Reward)
    return TicketYield(
        message=f'Success: Added comment to {item_type} {obj.id}.',
        focus_yield=3,
        xp_yield=15,
    )


# --- MAIN ORCHESTRATOR ---


@sync_to_async
def _ticket_sync(
    action: str, item_type: str, session_id: Optional[str] = None, **kwargs
) -> TicketYield:
    action = action.upper()
    item_type = item_type.upper()

    if action not in TicketConstants.VALID_ACTIONS:
        return TicketYield(
            TicketConstants.ERR_INVALID_ACTION.format(action=action)
        )
    if item_type not in TicketConstants.VALID_TYPES:
        return TicketYield(
            TicketConstants.ERR_INVALID_TYPE.format(item_type=item_type)
        )

    model_map = {
        TicketConstants.TYPE_EPIC: PFCEpic,
        TicketConstants.TYPE_STORY: PFCStory,
        TicketConstants.TYPE_TASK: PFCTask,
    }
    model_class = model_map[item_type]

    # FIX: Strip explicit Nones injected by the wrapper signature so dict logic behaves cleanly
    clean_kwargs = {k: v for k, v in kwargs.items() if v is not None}

    try:
        # Pre-calculate effective state for validations
        effective_state = clean_kwargs.copy()
        if action == TicketConstants.ACTION_UPDATE and clean_kwargs.get(
            'item_id'
        ):
            try:
                existing = model_class.objects.get(
                    id=clean_kwargs.get('item_id')
                )
                # Merge existing DB state with incoming payload
                for field in [
                    'perspective',
                    'assertions',
                    'outside',
                    'dependencies',
                    'demo_specifics',
                ]:
                    if field not in effective_state and hasattr(
                        existing, field
                    ):
                        effective_state[field] = getattr(existing, field)
                # Merge status
                if 'status' not in effective_state and getattr(
                    existing, 'status', None
                ):
                    effective_state['status'] = existing.status.name
            except ObjectDoesNotExist:
                pass

        # 1. Evaluate PAO Validation
        pao_err = _validate_pao(item_type, action, effective_state)
        if pao_err:
            return TicketYield(pao_err)

        # 2. Evaluate DoR Validation
        dor_err = _validate_dor(item_type, effective_state)
        if dor_err:
            return TicketYield(dor_err)

        # 3. Evaluate Complexity Shield
        comp_err = _validate_complexity(
            clean_kwargs.get('complexity'), session_id
        )
        if comp_err:
            return TicketYield(comp_err)

        # Execute Routing using clean_kwargs
        if action == TicketConstants.ACTION_READ:
            return _handle_read(
                model_class, item_type, clean_kwargs.get('item_id')
            )

        elif action == TicketConstants.ACTION_CREATE:
            return _handle_create(model_class, item_type, clean_kwargs)

        elif action == TicketConstants.ACTION_UPDATE:
            return _handle_update(
                model_class,
                item_type,
                clean_kwargs.get('item_id'),
                clean_kwargs,
            )

        elif action == TicketConstants.ACTION_COMMENT:
            return _handle_comment(
                model_class,
                item_type,
                clean_kwargs.get('item_id'),
                clean_kwargs.get('text'),
            )

    except ObjectDoesNotExist as e:
        return TicketYield(
            f'Error: Referenced object not found. Details: {str(e)}'
        )
    except Exception as e:
        logger.exception(f'[MCP Ticket] Execution crash: {e}')
        return TicketYield(f'Error executing ticket action: {str(e)}')


async def mcp_ticket(
    action: str,
    item_type: str,
    session_id: Optional[str] = None,
    item_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    name: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[int] = None,
    complexity: Optional[int] = None,
    perspective: Optional[str] = None,
    assertions: Optional[str] = None,
    outside: Optional[str] = None,
    dod_exceptions: Optional[str] = None,
    dependencies: Optional[str] = None,
    demo_specifics: Optional[str] = None,
    description: Optional[str] = None,
    text: Optional[str] = None,
) -> TicketYield:
    """
    MCP Tool: The master interface for the Agile Board.
    Enforces Experience Master validation rules (PAO, DoR) prior to DB operations.
    """
    return await _ticket_sync(
        action=action,
        item_type=item_type,
        session_id=session_id,
        item_id=item_id,
        parent_id=parent_id,
        name=name,
        status=status,
        priority=priority,
        complexity=complexity,
        perspective=perspective,
        assertions=assertions,
        outside=outside,
        dod_exceptions=dod_exceptions,
        dependencies=dependencies,
        demo_specifics=demo_specifics,
        description=description,
        text=text,
    )
