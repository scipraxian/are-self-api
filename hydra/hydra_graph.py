import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Callable, Dict

from django.http import HttpRequest, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from environments.variable_renderer import VariableRenderer

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
ACTION_UPDATE_BOOK = 'update_book'
ACTION_NODE_DETAILS = 'node_details'
ACTION_NODE_TELEMETRY = 'node_telemetry'
ACTION_SAVE_NODE_CONTEXT = 'save_node_context'

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
            ACTION_LIBRARY:
                get_library,
            ACTION_NODE_DETAILS:
                lambda book: get_node_details(book, request),
            ACTION_NODE_TELEMETRY:
                lambda book: get_node_telemetry(book, request),
            None:
                get_graph_layout,
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
            ACTION_UPDATE_BOOK: handle_update_book,
            ACTION_SAVE_NODE_CONTEXT: handle_save_node_context,
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

        title = n.invoked_spellbook.name if is_delegated else n.spell.name

        is_root = (n.spell_id == HydraSpell.BEGIN_PLAY) and not is_delegated

        node_data = {
            KEY_ID: n.id,
            KEY_TITLE: title,
            KEY_X: ui.get(KEY_X, 0),
            KEY_Y: ui.get(KEY_Y, 0),
            'spell_id': n.spell_id,
            KEY_IS_ROOT: is_root,
            'has_override': n.distribution_mode is not None,
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


def handle_update_book(book: HydraSpellbook, payload: dict) -> JsonResponse:
    new_name = payload.get('name')
    if new_name:
        book.name = new_name
        book.save(update_fields=['name'])
        return JsonResponse({KEY_STATUS: 'updated', 'name': book.name})
    return HttpResponseBadRequest('Name required')


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


def get_node_details(spellbook: HydraSpellbook,
                     request: HttpRequest) -> JsonResponse:
    node_id = request.GET.get('node_id')
    node = get_object_or_404(HydraSpellbookNode,
                             id=node_id,
                             spellbook=spellbook)

    # 1. Inspect the Spell to find variables
    # We look at all arguments and switches
    variables = set()

    if node.spell:
        # Check Args
        args = node.spell.hydraspellargumentassignment_set.all()
        for a in args:
            raw = a.argument.argument
            found = re.findall(r'\{\{\s*(\w+)\s*\}\}', raw)
            variables.update(found)

        # Check Switches
        switches = node.spell.switches.all()
        for s in switches:
            raw = s.flag + (s.value or '')
            found = re.findall(r'\{\{\s*(\w+)\s*\}\}', raw)
            variables.update(found)

        # Check Executable Args (Base args)
        exe_args = node.spell.talos_executable.talosexecutableargumentassignment_set.all(
        )
        for a in exe_args:
            raw = a.argument.argument
            found = re.findall(r'\{\{\s*(\w+)\s*\}\}', raw)
            variables.update(found)

    # 2. Get Global Context (Blue)
    # We use the spellbook's environment
    global_context = VariableRenderer.extract_variables(spellbook.environment)

    # 3. Get Overrides (Yellow)
    # HydraSpellBookNodeContext doesn't exist in imports, let's dynamic import or use related manager
    # node.hydraspellbooknodecontext_set assuming generic relation or we need to import model
    # The model name is HydraSpellBookNodeContext in models.py
    from .models import HydraSpellBookNodeContext

    overrides = {
        c.key: c.value for c in node.hydraspellbooknodecontext_set.all()
    }

    # Build the Smart Matrix
    matrix = []
    for var in sorted(list(variables)):
        item = {
            'key': var,
            'source': 'default',  # Green
            'value': '',
            'display_value': '',
            'is_readonly': False,
        }

        # Check Override (Highest Priority)
        if var in overrides:
            item['source'] = 'override'  # Yellow
            item['value'] = overrides[var]
            item['display_value'] = overrides[var]

        # Check Global
        elif var in global_context:
            item['source'] = 'global'  # Blue
            item['value'] = global_context[var]
            item['display_value'] = str(global_context[var])
            item['is_readonly'] = (
                True  # Globals are system managed usually? Or can we override them?
            )
            # User said "Input is read-only or shows 'System Managed'"

        matrix.append(item)

    return JsonResponse({
        'node_id': node.id,
        'name': node.spell.name if node.spell else 'Unknown',
        'description': node.spell.description if node.spell else '',
        'distribution_mode_id': node.distribution_mode_id,
        'context_matrix': matrix,
    })


def handle_save_node_context(spellbook: HydraSpellbook,
                             payload: dict) -> JsonResponse:
    node_id = payload.get('node_id')
    updates = payload.get('updates', [])  # List of {key, value}

    node = get_object_or_404(HydraSpellbookNode,
                             id=node_id,
                             spellbook=spellbook)

    from .models import HydraSpellBookNodeContext

    for update in updates:
        key = update.get('key')
        value = update.get('value')

        if not key:
            continue

        if not value:
            # Remove override if empty
            HydraSpellBookNodeContext.objects.filter(node=node,
                                                     key=key).delete()
        else:
            HydraSpellBookNodeContext.objects.update_or_create(
                node=node, key=key, defaults={'value': value})

    # Also handle distribution mode update
    dist_mode = payload.get('distribution_mode_id')
    if dist_mode:
        node.distribution_mode_id = dist_mode
        node.save(update_fields=['distribution_mode'])

    return JsonResponse({'status': 'saved'})


def get_node_telemetry(spellbook: HydraSpellbook,
                       request: HttpRequest) -> JsonResponse:
    node_id = request.GET.get('node_id')
    spawn_id = request.GET.get('spawn_id')

    if not spawn_id:
        return JsonResponse({'error': 'No spawn_id'}, status=400)

    # Get the latest Head for this node in this spawn
    # We join HydraHead -> HydraSpawn
    from .models import HydraHead, HydraSpawn, HydraSpellbookNode

    # We need the head belonging to the spawn.
    # The spawn might have multiple heads if looped, but usually we want the latest.
    head = (HydraHead.objects.filter(
        spawn_id=spawn_id, node_id=node_id).order_by('-created').first())

    if not head:
        return JsonResponse({'status': 'pending', 'logs': ''})

    # --- 1. LOGS ---
    # Spell Log (Standard Output usually)
    logs = head.spell_log or ''
    log_lines = logs.split('\n')
    spell_tail = log_lines[-20:] if len(log_lines) > 20 else log_lines

    # Execution Log (Wrapper Output)
    exec_logs = head.execution_log or ''
    exec_lines = exec_logs.split('\n')
    exec_tail = exec_lines[-20:] if len(exec_lines) > 20 else exec_lines

    # --- 2. COMMAND ---
    # Try to find the command in the execution log first (often printed by wrapper)
    # If not found, reconstruct it from the spell definition
    command = 'Command not captured.'
    if head.execution_log and 'Command:' in head.execution_log:
        # Simple heuristic if available
        pass

    # Let's reconstruct it "As Configured Now" (best effort if not snapshot)
    if head.spell:
        # We need to rebuild the context to get accurate command
        # This is expensive but requested.
        try:
            # Re-fetch node to be safe
            node = HydraSpellbookNode.objects.get(id=node_id)

            # Get Overrides (We assume they haven't changed since spawn for this view,
            # or we accept that this shows "Current Config" command)
            # The model name is HydraSpellBookNodeContext in models.py
            from .models import HydraSpellBookNodeContext

            overrides = {
                c.key: c.value
                for c in node.hydraspellbooknodecontext_set.all()
            }

            # We can't easily get the EXACT full command without the full context resolution
            # (including environment) which might have changed.
            # But let's call get_full_command with what we have.
            # We need the environment from the spellbook.
            cmd_list = head.spell.get_full_command(
                environment=spellbook.environment, extra_context=overrides)
            command = ' '.join(cmd_list)
        except Exception as e:
            command = f'Error interpreting command: {e}'

    # --- 3. CONTEXT PARAMETERS ---
    # We want to show what parameters were used.
    # We will reuse the logic from get_node_details but format for read-only.
    # Note: This shows CURRENT node config, not necessarily what ran if changed since.
    # To show what ran, we'd need to parse `head.execution_log` or `spawn.context_data`.
    # For now, we show "Current Configuration" context.

    # ... (Reusing logic from get_node_details, refactor recommended if reused often)
    # Copied logic for safety and speed:
    variables = set()
    if head.spell:
        # Args
        for a in head.spell.hydraspellargumentassignment_set.all():
            found = re.findall(r'\{\{\s*(\w+)\s*\}\}', a.argument.argument)
            variables.update(found)
        # Switches
        for s in head.spell.switches.all():
            found = re.findall(r'\{\{\s*(\w+)\s*\}\}', s.flag + (s.value or ''))
            variables.update(found)
        # Exec Args
        for (
                a
        ) in head.spell.talos_executable.talosexecutableargumentassignment_set.all(
        ):
            found = re.findall(r'\{\{\s*(\w+)\s*\}\}', a.argument.argument)
            variables.update(found)

    global_context = VariableRenderer.extract_variables(spellbook.environment)

    # If we have the node, get overrides
    overrides = {}
    if head.node:  # Should usually be true
        # The model name is HydraSpellBookNodeContext in models.py
        from .models import HydraSpellBookNodeContext
        overrides = {
            c.key: c.value
            for c in head.node.hydraspellbooknodecontext_set.all()
        }

    matrix = []
    for var in sorted(list(variables)):
        val = ''
        source = 'default'

        if var in overrides:
            val = overrides[var]
            source = 'override'
        elif var in global_context:
            val = str(global_context[var])
            source = 'global'

        matrix.append({'key': var, 'value': val, 'source': source})

    return JsonResponse({
        'status': head.status.name,
        'status_id': head.status_id,
        'agent': str(head.target) if head.target else 'Pending...',
        'exit_code': head.result_code,
        'logs': '\n'.join(spell_tail),  # Main Log (Spell Output)
        'exec_logs': '\n'.join(exec_tail),  # Wrapper Log (System)
        'command': command,
        'context_matrix': matrix,
        'head_id': str(head.id),
        'duration':
            '0s',  # Placeholder, implies calculation from created/modified
    })


def get_execution_status(spellbook: HydraSpellbook,
                         spawn_id: uuid.UUID = None) -> JsonResponse:
    """Returns the current state of the graph and the overall spawn status."""
    if not spawn_id:
        return JsonResponse({KEY_STATUS: STATUS_READY})

    try:
        # [FIX]: Fetch the actual spawn to get the real status (Success/Failed/Running)
        spawn = HydraSpawn.objects.select_related('status').get(id=spawn_id)

        node_status_map = {}
        # [FIX] Order by created so latest head overwrites previous ones for the same node
        for head in spawn.heads.all().order_by('created'):
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
