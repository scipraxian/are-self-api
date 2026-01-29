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
    HydraWireType,
)

logger = logging.getLogger(__name__)

# --- CONSTANTS ---

# URL Actions
ACTION_LIBRARY = 'library'
ACTION_STATUS = 'status'
ACTION_ADD_NODE = 'add_node'
ACTION_MOVE_NODE = 'move_node'
ACTION_CONNECT = 'connect'
ACTION_DELETE_NODE = 'delete_node'
ACTION_DISCONNECT = 'disconnect'

# Connection Types (Frontend Strings)
TYPE_FLOW_STR = 'flow'
TYPE_SUCCESS_STR = 'success'
TYPE_FAIL_STR = 'fail'

# JSON Response Keys
KEY_STATUS = 'status'
KEY_ID = 'id'
KEY_NODES = 'nodes'
KEY_CONNECTIONS = 'connections'
KEY_LIBRARY = 'library'
KEY_TITLE = 'title'
KEY_X = 'x'
KEY_Y = 'y'
KEY_IS_ROOT = 'is_root'

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
DEFAULT_UI_JSON_DICT = {KEY_X: 100, KEY_Y: 100}


# --- PAYLOADS ---


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
    type: str  # 'flow', 'success', 'fail'


@dataclass
class DeletePayload:
    node_id: int


# --- VIEW ROUTER ---


@method_decorator(csrf_exempt, name='dispatch')
class HydraGraphAPI(View):
    def get(self, request: HttpRequest, book_id: str, action: str = None):
        spellbook = get_object_or_404(HydraSpellbook, id=book_id)
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
        return HttpResponseBadRequest(f'Unknown action: {action}')


# --- LOGIC HANDLERS ---


def _ensure_begin_play_node(spellbook: HydraSpellbook) -> HydraSpellbookNode:
    """Guarantees the existence of the 'BeginPlay' anchor node."""
    node = spellbook.nodes.filter(spell_id=HydraSpell.BEGIN_PLAY).first()
    if not node:
        node = HydraSpellbookNode.objects.create(
            spellbook=spellbook,
            spell_id=HydraSpell.BEGIN_PLAY,
            ui_json=json.dumps(DEFAULT_UI_JSON_DICT),
        )
    return node


def get_graph_layout(spellbook: HydraSpellbook) -> JsonResponse:
    """
    Returns the graph layout.
    Maps HydraWireType IDs back to frontend strings ('success', 'fail', 'flow').
    """
    _ensure_begin_play_node(spellbook)

    nodes_data = []
    for n in spellbook.nodes.all().select_related('spell'):
        try:
            ui = json.loads(n.ui_json)
        except json.JSONDecodeError:
            ui = DEFAULT_UI_JSON_DICT

        nodes_data.append(
            {
                KEY_ID: n.id,
                KEY_TITLE: n.spell.name,
                KEY_X: ui.get(KEY_X, 0),
                KEY_Y: ui.get(KEY_Y, 0),
                'spell_id': n.spell_id,
                KEY_IS_ROOT: n.spell_id == HydraSpell.BEGIN_PLAY,
            }
        )

    # Map DB IDs to Frontend Strings for color coding
    # 1=Flow, 2=Success, 3=Failure
    type_to_string = {
        HydraWireType.TYPE_FLOW: TYPE_FLOW_STR,
        HydraWireType.TYPE_SUCCESS: TYPE_SUCCESS_STR,
        HydraWireType.TYPE_FAILURE: TYPE_FAIL_STR,
    }

    wires_data = []
    for w in spellbook.wires.all():
        wires_data.append(
            {
                'from_node_id': w.source_id,
                'to_node_id': w.target_id,
                # Frontend expects 'status_id' key with 'success'/'fail' strings
                'status_id': type_to_string.get(w.type_id, TYPE_FLOW_STR),
            }
        )

    return JsonResponse({KEY_NODES: nodes_data, KEY_CONNECTIONS: wires_data})


def handle_connect(book: HydraSpellbook, data: dict) -> JsonResponse:
    """
    Connects two nodes using HydraWireType.
    """
    p = ConnectPayload(**data)

    # Map frontend string ('success', etc) to DB ID (2, etc)
    string_to_type = {
        TYPE_FLOW_STR: HydraWireType.TYPE_FLOW,
        TYPE_SUCCESS_STR: HydraWireType.TYPE_SUCCESS,
        TYPE_FAIL_STR: HydraWireType.TYPE_FAILURE,
    }

    # Default to FLOW (White Wire) if unknown
    wire_type_id = string_to_type.get(p.type, HydraWireType.TYPE_FLOW)

    wire, created = HydraSpellbookConnectionWire.objects.get_or_create(
        spellbook=book,
        source_id=p.source_node_id,
        target_id=p.target_node_id,
        defaults={'type_id': wire_type_id},
    )

    # Update type if connection existed but changed color
    if not created and wire.type_id != wire_type_id:
        wire.type_id = wire_type_id
        wire.save()

    return JsonResponse({KEY_ID: wire.id, KEY_STATUS: STATUS_CONNECTED})


# --- STANDARD HANDLERS (Unchanged logic, just context) ---


def handle_move_node(book: HydraSpellbook, data: dict) -> JsonResponse:
    p = MovePayload(**data)
    node = get_object_or_404(HydraSpellbookNode, id=p.node_id, spellbook=book)
    node.ui_json = json.dumps({KEY_X: p.x, KEY_Y: p.y})
    node.save(update_fields=['ui_json'])
    return JsonResponse({KEY_STATUS: STATUS_MOVED})


def handle_disconnect(book: HydraSpellbook, data: dict) -> JsonResponse:
    source_id = data.get('source_node_id')
    target_id = data.get('target_node_id')
    HydraSpellbookConnectionWire.objects.filter(
        spellbook=book, source_id=source_id, target_id=target_id
    ).delete()
    return JsonResponse({KEY_STATUS: STATUS_DISCONNECTED})


def handle_delete_node(book: HydraSpellbook, data: dict) -> JsonResponse:
    p = DeletePayload(**data)
    node = get_object_or_404(HydraSpellbookNode, id=p.node_id, spellbook=book)
    if node.spell_id == HydraSpell.BEGIN_PLAY:
        return JsonResponse(
            {KEY_STATUS: STATUS_ERROR, MESSAGE: 'Cannot delete BeginPlay'},
            status=400,
        )
    node.delete()
    return JsonResponse({KEY_STATUS: STATUS_DELETED})


def handle_add_node(book: HydraSpellbook, data: dict) -> JsonResponse:
    p = NodePayload(**data)
    node = HydraSpellbookNode.objects.create(
        spellbook=book,
        spell_id=p.spell_id,
        ui_json=json.dumps({KEY_X: p.x, KEY_Y: p.y}),
    )
    return JsonResponse({KEY_ID: node.id, KEY_STATUS: STATUS_CREATED})


def get_library(spellbook: HydraSpellbook) -> JsonResponse:
    spells = HydraSpell.objects.values('id', 'name', 'distribution_mode__name')
    return JsonResponse({KEY_LIBRARY: list(spells)})


def get_execution_status(spellbook: HydraSpellbook) -> JsonResponse:
    return JsonResponse({KEY_STATUS: STATUS_READY})


class HydraGraphLaunchAPI(View):
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
