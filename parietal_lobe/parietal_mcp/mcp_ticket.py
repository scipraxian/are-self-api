import logging
from typing import Optional

from asgiref.sync import sync_to_async
from django.core.exceptions import ObjectDoesNotExist

from prefrontal_cortex.models import (
    PFCComment,
    PFCEpic,
    PFCItemStatus,
    PFCStory,
    PFCTask,
)

logger = logging.getLogger(__name__)


@sync_to_async
def _ticket_sync(
    action: str,
    item_type: str,
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
) -> str:
    """Synchronous execution of the Agile Board operations."""
    action = action.upper()
    item_type = item_type.upper()

    if action not in ['CREATE', 'READ', 'UPDATE', 'COMMENT']:
        return f"Error: Invalid action '{action}'. Must be CREATE, READ, UPDATE, or COMMENT."
    if item_type not in ['EPIC', 'STORY', 'TASK']:
        return f"Error: Invalid item_type '{item_type}'. Must be EPIC, STORY, or TASK."

    model_map = {'EPIC': PFCEpic, 'STORY': PFCStory, 'TASK': PFCTask}
    model_class = model_map[item_type]

    def get_status_obj(status_str: str) -> Optional[PFCItemStatus]:
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

    try:
        if action == 'READ':
            if not item_id:
                return f"Error: 'item_id' is required to READ a {item_type}."
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
            if item_type == 'EPIC':
                comments = obj.comments.all().order_by('created')
                children = obj.stories.all()
                if children.exists():
                    res.append('Child Stories:')
                    for c in children:
                        res.append(f'- {c.id} | {c.name} [{c.status.name}]')
            elif item_type == 'STORY':
                comments = obj.comments.all().order_by('created')
                children = obj.tasks.all()
                if children.exists():
                    res.append('\nChild Tasks:')
                    for c in children:
                        res.append(f'- {c.id} | {c.name} [{c.status.name}]')
            elif item_type == 'TASK':
                comments = obj.comments.all().order_by('created')

            if comments:
                res.append('\nComments:')
                for c in comments:
                    author = c.user.username if c.user else 'Talos'
                    res.append(
                        f'[{c.created.strftime("%Y-%m-%d %H:%M")}] {author}: {c.text}'
                    )

            return '\n'.join(res)

        elif action == 'CREATE':
            if not name:
                return "Error: 'name' is required for CREATE action."

            kwargs = {'name': name}
            status_obj = get_status_obj(status)
            if status_obj:
                kwargs['status'] = status_obj

            if item_type == 'STORY':
                if not parent_id:
                    return "Error: 'parent_id' (Epic UUID) is required to create a STORY."
                kwargs['epic'] = PFCEpic.objects.get(id=parent_id)
            elif item_type == 'TASK':
                if not parent_id:
                    return "Error: 'parent_id' (Story UUID) is required to create a TASK."
                kwargs['story'] = PFCStory.objects.get(id=parent_id)

            if description is not None:
                kwargs['description'] = description
            if perspective is not None:
                kwargs['perspective'] = perspective
            if assertions is not None:
                kwargs['assertions'] = assertions
            if outside is not None:
                kwargs['outside'] = outside
            if dod_exceptions is not None:
                kwargs['dod_exceptions'] = dod_exceptions
            if dependencies is not None:
                kwargs['dependencies'] = dependencies
            if demo_specifics is not None:
                kwargs['demo_specifics'] = demo_specifics
            if priority is not None:
                kwargs['priority'] = priority

            # Catch complexity if it is active on the model
            if complexity is not None and hasattr(model_class, 'complexity'):
                kwargs['complexity'] = complexity

            obj = model_class.objects.create(**kwargs)
            return (
                f"Success: Created {item_type} '{obj.name}' with ID: {obj.id}"
            )

        elif action == 'UPDATE':
            if not item_id:
                return f"Error: 'item_id' is required to UPDATE a {item_type}."
            obj = model_class.objects.get(id=item_id)

            if name is not None:
                obj.name = name
            status_obj = get_status_obj(status)
            if status_obj:
                obj.status = status_obj

            if description is not None:
                obj.description = description
            if perspective is not None:
                obj.perspective = perspective
            if assertions is not None:
                obj.assertions = assertions
            if outside is not None:
                obj.outside = outside
            if dod_exceptions is not None:
                obj.dod_exceptions = dod_exceptions
            if dependencies is not None:
                obj.dependencies = dependencies
            if demo_specifics is not None:
                obj.demo_specifics = demo_specifics
            if priority is not None:
                obj.priority = priority

            if complexity is not None and hasattr(obj, 'complexity'):
                obj.complexity = complexity

            obj.save()
            return f'Success: Updated {item_type} {obj.id}.'

        elif action == 'COMMENT':
            if not item_id:
                return (
                    f"Error: 'item_id' is required to COMMENT on a {item_type}."
                )
            if not text:
                return "Error: 'text' is required for COMMENT action."

            obj = model_class.objects.get(id=item_id)
            kwargs = {'text': text}

            if item_type == 'EPIC':
                kwargs['epic'] = obj
            elif item_type == 'STORY':
                kwargs['story'] = obj
            elif item_type == 'TASK':
                kwargs['task'] = obj

            PFCComment.objects.create(**kwargs)
            return f'Success: Added comment to {item_type} {obj.id}.'

    except ObjectDoesNotExist as e:
        return f'Error: Referenced object not found. Details: {str(e)}'
    except Exception as e:
        logger.exception(f'[MCP Ticket] Execution crash: {e}')
        return f'Error executing ticket action: {str(e)}'


async def mcp_ticket(
    action: str,
    item_type: str,
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
) -> str:
    """
    MCP Tool: The master interface for the Agile Board.
    Use this to CREATE, READ, UPDATE, or COMMENT on Epics, Stories, and Tasks.
    """
    return await _ticket_sync(
        action=action,
        item_type=item_type,
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
