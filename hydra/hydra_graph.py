import json
import logging
from dataclasses import dataclass
from typing import Callable, Dict

from django.http import HttpRequest, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .hydra import Hydra
from .models import (
    HydraSpell,
    HydraSpellbook,
    HydraSpellbookConnectionWire,
    HydraSpellbookNode,
    HydraStatusID,
)

logger = logging.getLogger(__name__)

# --- CONSTANTS (The Registry) ---

# URL Actions
ACTION_LIBRARY = 'library'
ACTION_STATUS = 'status'
ACTION_ADD_NODE = 'add_node'
ACTION_MOVE_NODE = 'move_node'
ACTION_CONNECT = 'connect'
ACTION_DELETE_NODE = 'delete_node'
ACTION_DISCONNECT = 'disconnect'

# Connection Types
TYPE_FLOW = 'flow'
TYPE_SUCCESS = 'success'
TYPE_FAIL = 'fail'

# JSON Response Keys
KEY_STATUS = 'status'
KEY_ID = 'id'
KEY_NODES = 'nodes'
KEY_CONNECTIONS = 'connections'
KEY_LIBRARY = 'library'
KEY_TITLE = 'title'
KEY_X = 'x'
KEY_Y = 'y'

# Status Values
STATUS_CREATED = 'created'
STATUS_MOVED = 'moved'
STATUS_CONNECTED = 'connected'
STATUS_DELETED = 'deleted'
STATUS_DISCONNECTED = 'disconnected'
STATUS_READY = 'ready'
STATUS_STARTED = 'started'
STATUS_ERROR = 'error'

ERROR_STATUS_CODE = 500

SPAWN_ID = 'spawn_id'
MESSAGE = 'message'


# --- 1. Strict Payload Definitions ---


@dataclass
class NodePayload:
    spell_id: int
    x: int
    y: int


@dataclass
class MovePayload:
    node_id: int
    x: int
    y: int


@dataclass
class ConnectPayload:
    source_node_id: int
    target_node_id: int
    type: str


@dataclass
class DeletePayload:
    node_id: int


# --- 2. The View Router (CBV) ---


@method_decorator(csrf_exempt, name='dispatch')
class HydraGraphAPI(View):
    """
    JSON API for the Visual Graph Editor.
    Routes actions to standalone functional handlers via Dict lookups.
    """

    def get(self, request: HttpRequest, book_id: str, action: str = None):
        spellbook = get_object_or_404(HydraSpellbook, id=book_id)

        # Dispatch Map for Read Operations
        # Default behavior (None) maps to get_graph_layout
        dispatch_map: Dict[str | None, Callable] = {
            ACTION_LIBRARY: get_library,
            ACTION_STATUS: get_execution_status,
            None: get_graph_layout,
        }

        handler = dispatch_map.get(action)
        if handler:
            return handler(spellbook)

        return HttpResponseBadRequest(f'Unknown graph action: {action}')

    def post(self, request: HttpRequest, book_id: str, action: str):
        spellbook = get_object_or_404(HydraSpellbook, id=book_id)

        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return HttpResponseBadRequest('Invalid JSON')

        # Dispatch Map for Write Operations
        dispatch_map: Dict[str, Callable] = {
            ACTION_ADD_NODE: handle_add_node,
            ACTION_MOVE_NODE: handle_move_node,
            ACTION_CONNECT: handle_connect,
            ACTION_DELETE_NODE: handle_delete_node,
            ACTION_DISCONNECT: handle_disconnect,
        }

        handler = dispatch_map.get(action)
        if handler:
            return handler(spellbook, payload)

        return HttpResponseBadRequest(f'Unknown graph action: {action}')


# --- 3. Logic Handlers (Functional Controllers) ---


def get_library(spellbook: HydraSpellbook) -> JsonResponse:
    """Returns available Spells for the sidebar."""
    spells = HydraSpell.objects.values('id', 'name', 'distribution_mode__name')
    return JsonResponse({KEY_LIBRARY: list(spells)})


def get_graph_layout(spellbook: HydraSpellbook) -> JsonResponse:
    """Reconstructs the graph JSON from the Database."""
    nodes = []
    # Use select_related to avoid N+1 queries on the Spell table
    for n in spellbook.nodes.all().select_related('spell'):
        try:
            ui = json.loads(n.ui_json)
        except (TypeError, json.JSONDecodeError):
            ui = {KEY_X: 0, KEY_Y: 0}

        nodes.append(
            {
                KEY_ID: n.id,
                KEY_TITLE: n.spell.name,
                KEY_X: ui.get(KEY_X, 0),
                KEY_Y: ui.get(KEY_Y, 0),
                'spell_id': n.spell_id,
            }
        )

    wires = []
    for w in spellbook.wires.all():
        wires.append(
            {
                'from_node_id': w.source_id,
                'to_node_id': w.target_id,
                'status_id': w.status_id,
            }
        )

    return JsonResponse({KEY_NODES: nodes, KEY_CONNECTIONS: wires})


def get_execution_status(spellbook: HydraSpellbook) -> JsonResponse:
    """Returns live status of the latest spawn."""
    # Placeholder for live monitoring integration
    return JsonResponse({KEY_STATUS: STATUS_READY})


def handle_add_node(book: HydraSpellbook, data: dict) -> JsonResponse:
    p = NodePayload(**data)

    node = HydraSpellbookNode.objects.create(
        spellbook=book,
        spell_id=p.spell_id,
        ui_json=json.dumps({KEY_X: p.x, KEY_Y: p.y}),
    )
    return JsonResponse({KEY_ID: node.id, KEY_STATUS: STATUS_CREATED})


def handle_move_node(book: HydraSpellbook, data: dict) -> JsonResponse:
    p = MovePayload(**data)

    node = get_object_or_404(HydraSpellbookNode, id=p.node_id, spellbook=book)
    node.ui_json = json.dumps({KEY_X: p.x, KEY_Y: p.y})
    node.save(update_fields=['ui_json'])

    return JsonResponse({KEY_STATUS: STATUS_MOVED})


def handle_connect(book: HydraSpellbook, data: dict) -> JsonResponse:
    p = ConnectPayload(**data)

    status_map = {
        TYPE_FLOW: HydraStatusID.SUCCESS,
        TYPE_SUCCESS: HydraStatusID.SUCCESS,
        TYPE_FAIL: HydraStatusID.FAILED,
    }
    status_id = status_map.get(p.type, HydraStatusID.SUCCESS)

    wire, created = HydraSpellbookConnectionWire.objects.get_or_create(
        spellbook=book,
        source_id=p.source_node_id,
        target_id=p.target_node_id,
        defaults={'status_id': status_id},
    )

    if not created and wire.status_id != status_id:
        wire.status_id = status_id
        wire.save()

    return JsonResponse({KEY_ID: wire.id, KEY_STATUS: STATUS_CONNECTED})


def handle_delete_node(book: HydraSpellbook, data: dict) -> JsonResponse:
    p = DeletePayload(**data)
    HydraSpellbookNode.objects.filter(id=p.node_id, spellbook=book).delete()
    return JsonResponse({KEY_STATUS: STATUS_DELETED})


def handle_disconnect(book: HydraSpellbook, data: dict) -> JsonResponse:
    source_id = data.get('source_node_id')
    target_id = data.get('target_node_id')
    HydraSpellbookConnectionWire.objects.filter(
        spellbook=book, source_id=source_id, target_id=target_id
    ).delete()
    return JsonResponse({KEY_STATUS: STATUS_DISCONNECTED})


class HydraGraphLaunchAPI(View):
    """
    API Endpoint to launch a Spellbook from the Graph Editor.
    Uses the URL parameter for context, no JSON parsing required.
    """

    def post(self, request, book_id):
        try:
            controller = Hydra(spellbook_id=book_id)
            controller.start()
            return JsonResponse(
                {
                    ACTION_STATUS: STATUS_STARTED,
                    SPAWN_ID: str(controller.spawn.id),
                }
            )
        except Exception as e:
            logger.exception('[HYDRA] Graph Launch Failed')
            return JsonResponse(
                {ACTION_STATUS: STATUS_ERROR, MESSAGE: str(e)},
                status=ERROR_STATUS_CODE,
            )
