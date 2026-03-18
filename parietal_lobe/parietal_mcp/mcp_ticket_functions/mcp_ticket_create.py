from asgiref.sync import sync_to_async

from frontal_lobe.models import ReasoningSession
from prefrontal_cortex.models import PFCEpic, PFCStory, PFCTask
from prefrontal_cortex.serializers import (
    PFCEpicSerializer,
    PFCStorySerializer,
    PFCTaskSerializer,
    TicketAction,
    make_action_response,
)

MODEL_MAP = {
    'EPIC': (PFCEpic, PFCEpicSerializer),
    'STORY': (PFCStory, PFCStorySerializer),
    'TASK': (PFCTask, PFCTaskSerializer),
}


@sync_to_async
def _create_sync(
    item_type: str | None,
    field_value: str | None = None,
    parent_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """
    Create a new ticket using a flat argument model.
    """
    item_type_normalized = str(item_type or '').upper()
    if item_type_normalized not in MODEL_MAP:
        return make_action_response(
            action=TicketAction.CREATE,
            ok=False,
            item_type=item_type_normalized,
            error=(
                f"Invalid item_type '{item_type_normalized}'. "
                'Must be EPIC, STORY, or TASK.'
            ),
        )

    if not (field_value or '').strip():
        return make_action_response(
            action=TicketAction.CREATE,
            ok=False,
            item_type=item_type_normalized,
            error='field_value (ticket name) is required for create.',
        )

    _, serializer_class = MODEL_MAP[item_type_normalized]

    payload: dict = {'name': field_value}

    # Map parent relationships & Environments
    if item_type_normalized == 'EPIC':
        if not session_id:
            return make_action_response(
                action=TicketAction.CREATE,
                ok=False,
                item_type=item_type_normalized,
                error='SYSTEM ERROR: session_id is required to assign environment to Epic.',
            )
        try:
            # Trace the session back to the environment
            session = ReasoningSession.objects.select_related(
                'spike__spike_train'
            ).get(id=session_id)
            payload['environment'] = session.spike.spike_train.environment_id
        except ReasoningSession.DoesNotExist:
            return make_action_response(
                action=TicketAction.CREATE,
                ok=False,
                item_type=item_type_normalized,
                error='SYSTEM ERROR: Could not locate active ReasoningSession.',
            )

    elif item_type_normalized == 'STORY' and parent_id:
        payload['epic'] = parent_id
    elif item_type_normalized == 'TASK' and parent_id:
        payload['story'] = parent_id

    serializer = serializer_class(data=payload)
    if serializer.is_valid():
        instance = serializer.save()
        return make_action_response(
            action=TicketAction.CREATE,
            item_type=item_type_normalized,
            item_id=instance.id,
            data=serializer.data,
        )

    return make_action_response(
        action=TicketAction.CREATE,
        ok=False,
        item_type=item_type_normalized,
        error=f'VALIDATION ERROR: {serializer.errors}',
    )


async def execute(
    item_type: str | None = None,
    field_value: str | None = None,
    parent_id: str | None = None,
    session_id: str | None = None,
    **_: object,
) -> str:
    """Implementation of ticket creation using flat arguments."""
    return await _create_sync(
        item_type=item_type,
        field_value=field_value,
        parent_id=parent_id,
        session_id=session_id,
    )
