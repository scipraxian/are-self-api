import json
import logging
import uuid
from dataclasses import dataclass
from typing import Callable, Dict

from django.http import HttpRequest, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .hydra import Hydra
from .models import (
    HydraSpawn,
    HydraSpell,
    HydraSpellbook,
    HydraSpellbookConnectionWire,
    HydraSpellbookNode,
    HydraStatusID,
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
    spell_id: int | None
    invoked_spellbook_id: str | None  # UUID
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
        if action == ACTION_STATUS:
            spawn_id = request.GET.get('spawn_id')
            return get_execution_status(spellbook, spawn_id)

        dispatch_map: Dict[str | None, Callable] = {
            ACTION_LIBRARY: get_library,
            None: get_graph_layout,
        }
        handler = dispatch_map.get(action)
        if handler:
            return handler(spellbook)
        return HttpResponseBadRequest(f'Unknown action: {action}')

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
    node = spellbook.nodes.filter(is_root=True).first()
    if not node:
        node = HydraSpellbookNode.objects.create(
            spellbook=spellbook,
            spell_id=HydraSpell.BEGIN_PLAY,
            is_root=True,
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

        is_delegated = bool(n.invoked_spellbook_id)

        # [FIX] Visual Logic
        # 1. Title: Use Spellbook Name if delegated
        title = n.invoked_spellbook.name if is_delegated else n.spell.name

        # 2. Root Status: Delegated nodes are never roots, even if they use the placeholder ID
        is_root = (n.spell_id == HydraSpell.BEGIN_PLAY) and not is_delegated

        node_data = {
            KEY_ID: n.id,
            KEY_TITLE: title,
            KEY_X: ui.get(KEY_X, 0),
            KEY_Y: ui.get(KEY_Y, 0),
            'spell_id': n.spell_id,
            KEY_IS_ROOT: is_root,
        }

        if is_delegated:
            node_data['invoked_spellbook_id'] = str(n.invoked_spellbook_id)

        nodes_data.append(node_data)

    # Map DB IDs to Frontend Strings for color coding
    # 1=Flow, 2=Success, 3=Failure
    type_to_string = {
        HydraWireType.TYPE_FLOW: TYPE_FLOW_STR,
        HydraWireType.TYPE_SUCCESS: TYPE_SUCCESS_STR,
        HydraWireType.TYPE_FAILURE: TYPE_FAIL_STR,
    }

    wires_data = []
    for w in spellbook.wires.all():
        wires_data.append({
            'from_node_id': w.source_id,
            'to_node_id': w.target_id,
            # Frontend expects 'status_id' key with 'success'/'fail' strings
            'status_id': type_to_string.get(w.type_id, TYPE_FLOW_STR),
        })

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
    HydraSpellbookConnectionWire.objects.filter(spellbook=book,
                                                source_id=source_id,
                                                target_id=target_id).delete()
    return JsonResponse({KEY_STATUS: STATUS_DISCONNECTED})


def handle_delete_node(book: HydraSpellbook, data: dict) -> JsonResponse:
    p = DeletePayload(**data)
    node = get_object_or_404(HydraSpellbookNode, id=p.node_id, spellbook=book)
    # [FIX] Delegated nodes might use BEGIN_PLAY ID as placeholder, but they ARE deletable.
    # So we only block deletion if it's NOT delegated AND is explicitly the root anchor.
    is_delegated = bool(node.invoked_spellbook_id)
    if not is_delegated and node.spell_id == HydraSpell.BEGIN_PLAY:
        return JsonResponse(
            {
                KEY_STATUS: STATUS_ERROR,
                MESSAGE: 'Cannot delete BeginPlay'
            },
            status=400,
        )
    node.delete()
    return JsonResponse({KEY_STATUS: STATUS_DELETED})


def handle_add_node(spellbook: HydraSpellbook, payload: dict) -> JsonResponse:
    spell_id = payload.get('spell_id')
    invoked_book_id = payload.get('invoked_spellbook_id')

    is_root = False

    if invoked_book_id:
        # It's a Sub-Graph Node
        # We need a placeholder Spell to satisfy the DB constraint.
        # Ideally, we have a specific 'SubGraph' spell.
        # For now, we'll try to find one named 'SubGraph' or fallback to the first available non-root.
        # This is a bit hacky but keeps schema simple.

        # Try to find a spell that looks like a runner
        dummy_spell = HydraSpell.objects.filter(
            name__icontains='Sub-Graph').first()
        if not dummy_spell:
            dummy_spell = HydraSpell.objects.first()  # Emergency fallback

        spell_id = dummy_spell.id
    else:
        # Standard Spell
        if int(spell_id) == HydraSpell.BEGIN_PLAY:
            if spellbook.nodes.filter(is_root=True).exists():
                return JsonResponse(
                    {'error': 'Begin Play node already exists.'}, status=400)
            is_root = True

    ui_data = {'x': payload.get('x', 0), 'y': payload.get('y', 0)}

    node = HydraSpellbookNode.objects.create(
        spellbook=spellbook,
        spell_id=spell_id,
        invoked_spellbook_id=invoked_book_id,  # <--- NEW FIELD
        is_root=is_root,
        ui_json=json.dumps(ui_data),
    )
    return JsonResponse({'id': str(node.id)})


def get_library(spellbook: HydraSpellbook) -> JsonResponse:
    # 1. Standard Spells
    spells = list(
        HydraSpell.objects.values('id', 'name', 'distribution_mode__name'))
    # Tag them as 'Spells'
    for s in spells:
        s['category'] = 'Spells'

    # 2. Sub-Graphs (Spellbooks)
    # Exclude self to prevent recursion!
    books = HydraSpellbook.objects.exclude(id=spellbook.id).values('id', 'name')
    for b in books:
        b['category'] = 'Sub-Graphs'
        # We need to distinguish IDs. Let's send them as `invoked_spellbook_id` or similar
        # But `add_node` needs to handle it.
        # Ideally, we structure the payload so the frontend knows it's a book.
        b['is_book'] = True

    # Combine
    return JsonResponse({KEY_LIBRARY: spells + list(books)})


def get_execution_status(spellbook: HydraSpellbook,
                         spawn_id: uuid.UUID = None) -> JsonResponse:
    """Returns the current state of the graph and the overall spawn status."""
    if not spawn_id:
        return JsonResponse({KEY_STATUS: STATUS_READY})

    try:
        # [FIX]: Fetch the actual spawn to get the real status (Success/Failed/Running)
        spawn = HydraSpawn.objects.select_related('status').get(id=spawn_id)

        node_status_map = {}
        # Use the existing head relationship to populate node statuses
        for head in spawn.heads.all():
            if head.node_id:
                head_data = {
                    'status_id': head.status_id,
                    'head_id': str(head.id),
                }
                child = head.child_spawns.first()
                if child:
                    head_data['child_spawn_id'] = str(child.id)
                node_status_map[str(head.node_id)] = head_data

        # [FIX]: Return the real status name (e.g., "Success", "Failed")
        # instead of the hardcoded "running" string.
        return JsonResponse({
            KEY_STATUS: spawn.status.name,
            'nodes': node_status_map
        })
    except HydraSpawn.DoesNotExist:
        return JsonResponse({
            KEY_STATUS: STATUS_ERROR,
            MESSAGE: 'Spawn not found'
        })
    except Exception as e:
        logger.exception('Status Check Failed')
        return JsonResponse({KEY_STATUS: STATUS_ERROR, MESSAGE: str(e)})


class HydraGraphLaunchAPI(View):

    def post(self, request, book_id):
        try:
            controller = Hydra(spellbook_id=book_id)
            controller.start()
            return JsonResponse({
                ACTION_STATUS: STATUS_STARTED,
                SPAWN_ID: str(controller.spawn.id),
            })
        except Exception as e:
            logger.exception('[HYDRA] Graph Launch Failed')
            return JsonResponse(
                {
                    ACTION_STATUS: STATUS_ERROR,
                    MESSAGE: str(e)
                },
                status=ERROR_STATUS_CODE,
            )


class HydraGraphSpawnStatusAPI(View):

    def get(self, request, spawn_id):
        spawn = get_object_or_404(HydraSpawn, id=spawn_id)

        heads = spawn.heads.all().order_by('created')
        node_status_map = {}

        # Special Case: Begin Play Node (always green once spawn exists)
        begin_play_node = spawn.spellbook.nodes.filter(
            spell_id=HydraSpell.BEGIN_PLAY).first()
        if begin_play_node:
            node_status_map[str(begin_play_node.id)] = {
                'status_id': HydraStatusID.SUCCESS,
                'head_id': None,
            }

        for head in heads:
            if head.node_id:
                node_status_map[str(head.node_id)] = {
                    'status_id': head.status_id,
                    'head_id': str(head.id),
                }

        return JsonResponse({
            'status_label': spawn.status.name,
            'is_active': spawn.is_active,
            'nodes': node_status_map,
        })
