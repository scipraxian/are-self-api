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

from .central_nervous_system import CNS
from .models import (
    Axon,
    AxonType,
    CNSStatusID,
    Effector,
    NeuralPathway,
    Neuron,
    Spike,
    SpikeTrain,
)

logger = logging.getLogger(__name__)

# --- CONSTANTS ---

# URL Actions
ACTION_LIBRARY = 'library'
ACTION_STATUS = 'status'
ACTION_ADD_NEURON = 'add_neuron'
ACTION_MOVE_NEURON = 'move_neuron'
ACTION_CONNECT = 'connect'
ACTION_DELETE_NEURON = 'delete_neuron'
ACTION_DISCONNECT = 'disconnect'
ACTION_UPDATE_PATHWAY = 'update_pathway'
ACTION_NEURON_DETAILS = 'neuron_details'
ACTION_NEURON_TELEMETRY = 'neuron_telemetry'
ACTION_SAVE_NEURON_CONTEXT = 'save_neuron_context'

# Connection Types (Frontend Strings)
TYPE_FLOW_STR = 'flow'
TYPE_SUCCESS_STR = 'success'
TYPE_FAIL_STR = 'fail'

# JSON Response Keys
KEY_STATUS = 'status'
KEY_ID = 'id'
KEY_NEURONS = 'neurons'
KEY_AXONS = 'axons'
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
SPIKE_TRAIN_ID = 'spike_train_id'
MESSAGE = 'message'
DEFAULT_UI_JSON_DICT = {KEY_X: 100, KEY_Y: 100}

# --- PAYLOADS ---


@dataclass
class NeuronPayload:
    effector_id: int | None
    invoked_pathway_id: str | None  # UUID
    x: int
    y: int


@dataclass
class MovePayload:
    neuron_id: int
    x: int
    y: int


@dataclass
class ConnectPayload:
    source_neuron_id: int
    target_neuron_id: int
    type: str  # 'flow', 'success', 'fail'


@dataclass
class DeletePayload:
    neuron_id: int


# --- VIEW ROUTER ---


@method_decorator(csrf_exempt, name='dispatch')
class CNSGraphAPI(View):
    def get(self, request: HttpRequest, pathway_id: str, action: str = None):
        pathway = get_object_or_404(NeuralPathway, id=pathway_id)
        if action == ACTION_STATUS:
            spike_train_id = request.GET.get('spike_train_id')
            return get_execution_status(pathway, spike_train_id)

        dispatch_map: Dict[str | None, Callable] = {
            ACTION_LIBRARY: get_library,
            ACTION_NEURON_DETAILS: lambda pathway: get_neuron_details(
                pathway, request
            ),
            ACTION_NEURON_TELEMETRY: lambda pathway: get_neuron_telemetry(
                pathway, request
            ),
            None: get_graph_layout,
        }
        handler = dispatch_map.get(action)
        if handler:
            return handler(pathway)
        return HttpResponseBadRequest(f'Unknown action: {action}')

    def post(self, request: HttpRequest, pathway_id: str, action: str):
        pathway = get_object_or_404(NeuralPathway, id=pathway_id)
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return HttpResponseBadRequest('Invalid JSON')

        dispatch_map: Dict[str, Callable] = {
            ACTION_ADD_NEURON: handle_add_neuron,
            ACTION_MOVE_NEURON: handle_move_neuron,
            ACTION_CONNECT: handle_connect,
            ACTION_DELETE_NEURON: handle_delete_neuron,
            ACTION_DISCONNECT: handle_disconnect,
            ACTION_UPDATE_PATHWAY: handle_update_pathway,
            ACTION_SAVE_NEURON_CONTEXT: handle_save_neuron_context,
        }
        handler = dispatch_map.get(action)
        if handler:
            return handler(pathway, payload)
        return HttpResponseBadRequest(f'Unknown action: {action}')


# --- LOGIC HANDLERS ---


def _ensure_begin_play_neuron(pathway: NeuralPathway) -> Neuron:
    """Guarantees the existence of the 'BeginPlay' anchor neuron."""
    neuron = pathway.neurons.filter(is_root=True).first()
    if not neuron:
        neuron = Neuron.objects.create(
            pathway=pathway,
            effector_id=Effector.BEGIN_PLAY,
            is_root=True,
            ui_json=json.dumps(DEFAULT_UI_JSON_DICT),
        )
    return neuron


def get_graph_layout(pathway: NeuralPathway) -> JsonResponse:
    """
    Returns the graph layout.
    Maps AxonType IDs back to frontend strings ('success', 'fail', 'flow').
    """
    _ensure_begin_play_neuron(pathway)

    neurons_data = []
    for n in pathway.neurons.all().select_related('effector'):
        try:
            ui = json.loads(n.ui_json)
        except json.JSONDecodeError:
            ui = DEFAULT_UI_JSON_DICT

        is_delegated = bool(n.invoked_pathway_id)

        title = n.invoked_pathway.name if is_delegated else n.effector.name

        is_root = (n.effector_id == Effector.BEGIN_PLAY) and not is_delegated

        neuron_data = {
            KEY_ID: n.id,
            KEY_TITLE: title,
            KEY_X: ui.get(KEY_X, 0),
            KEY_Y: ui.get(KEY_Y, 0),
            'effector_id': n.effector_id,
            KEY_IS_ROOT: is_root,
            'has_override': n.distribution_mode is not None,
        }

        if is_delegated:
            neuron_data['invoked_pathway_id'] = str(n.invoked_pathway_id)

        neurons_data.append(neuron_data)

    # Map DB IDs to Frontend Strings for color coding
    # 1=Flow, 2=Success, 3=Failure
    type_to_string = {
        AxonType.TYPE_FLOW: TYPE_FLOW_STR,
        AxonType.TYPE_SUCCESS: TYPE_SUCCESS_STR,
        AxonType.TYPE_FAILURE: TYPE_FAIL_STR,
    }

    axons_data = []
    for w in pathway.axons.all():
        axons_data.append(
            {
                'source_neuron_id': w.source_id,
                'target_neuron_id': w.target_id,
                # Frontend expects 'status_id' key with 'success'/'fail' strings
                'status_id': type_to_string.get(w.type_id, TYPE_FLOW_STR),
            }
        )

    return JsonResponse({KEY_NEURONS: neurons_data, KEY_AXONS: axons_data})


def handle_connect(pathway: NeuralPathway, data: dict) -> JsonResponse:
    """
    Connects two neurons using AxonType.
    """
    p = ConnectPayload(**data)

    # Map frontend string ('success', etc) to DB ID (2, etc)
    string_to_type = {
        TYPE_FLOW_STR: AxonType.TYPE_FLOW,
        TYPE_SUCCESS_STR: AxonType.TYPE_SUCCESS,
        TYPE_FAIL_STR: AxonType.TYPE_FAILURE,
    }

    # Default to FLOW (White Wire) if unknown
    axon_type_id = string_to_type.get(p.type, AxonType.TYPE_FLOW)

    axon, created = Axon.objects.get_or_create(
        pathway=pathway,
        source_id=p.source_neuron_id,
        target_id=p.target_neuron_id,
        defaults={'type_id': axon_type_id},
    )

    # Update type if connection existed but changed color
    if not created and axon.type_id != axon_type_id:
        axon.type_id = axon_type_id
        axon.save()

    return JsonResponse({KEY_ID: axon.id, KEY_STATUS: STATUS_CONNECTED})


# --- STANDARD HANDLERS ---


def handle_move_neuron(pathway: NeuralPathway, data: dict) -> JsonResponse:
    p = MovePayload(**data)
    neuron = get_object_or_404(Neuron, id=p.neuron_id, pathway=pathway)
    neuron.ui_json = json.dumps({KEY_X: p.x, KEY_Y: p.y})
    neuron.save(update_fields=['ui_json'])
    return JsonResponse({KEY_STATUS: STATUS_MOVED})


def handle_disconnect(pathway: NeuralPathway, data: dict) -> JsonResponse:
    source_id = data.get('source_neuron_id')
    target_id = data.get('target_neuron_id')
    Axon.objects.filter(
        pathway=pathway, source_id=source_id, target_id=target_id
    ).delete()
    return JsonResponse({KEY_STATUS: STATUS_DISCONNECTED})


def handle_update_pathway(
    pathway: NeuralPathway, payload: dict
) -> JsonResponse:
    new_name = payload.get('name')
    if new_name:
        pathway.name = new_name
        pathway.save(update_fields=['name'])
        return JsonResponse({KEY_STATUS: 'updated', 'name': pathway.name})
    return HttpResponseBadRequest('Name required')


def handle_delete_neuron(pathway: NeuralPathway, data: dict) -> JsonResponse:
    p = DeletePayload(**data)
    neuron = get_object_or_404(Neuron, id=p.neuron_id, pathway=pathway)
    is_delegated = bool(neuron.invoked_pathway_id)
    if not is_delegated and neuron.effector_id == Effector.BEGIN_PLAY:
        return JsonResponse(
            {KEY_STATUS: STATUS_ERROR, MESSAGE: 'Cannot delete BeginPlay'},
            status=400,
        )
    neuron.delete()
    return JsonResponse({KEY_STATUS: STATUS_DELETED})


def handle_add_neuron(pathway: NeuralPathway, payload: dict) -> JsonResponse:
    effector_id = payload.get('effector_id')
    invoked_pathway_id = payload.get('invoked_pathway_id')

    is_root = False

    if invoked_pathway_id:
        dummy_effector = Effector.objects.filter(
            name__icontains='Sub-Graph'
        ).first()
        if not dummy_effector:
            dummy_effector = Effector.objects.first()  # Emergency fallback

        effector_id = dummy_effector.id
    else:
        # Standard Spell
        if int(effector_id) == Effector.BEGIN_PLAY:
            if pathway.neurons.filter(is_root=True).exists():
                return JsonResponse(
                    {'error': 'Begin Play neuron already exists.'}, status=400
                )
            is_root = True

    ui_data = {'x': payload.get('x', 0), 'y': payload.get('y', 0)}

    neuron = Neuron.objects.create(
        pathway=pathway,
        effector_id=effector_id,
        invoked_pathway_id=invoked_pathway_id,
        is_root=is_root,
        ui_json=json.dumps(ui_data),
    )
    return JsonResponse({'id': str(neuron.id)})


def get_library(pathway: NeuralPathway) -> JsonResponse:
    # 1. Standard Spells
    effectors = list(
        Effector.objects.values('id', 'name', 'distribution_mode__name')
    )
    # Tag them as 'Spells'
    for s in effectors:
        s['category'] = 'Spells'

    # 2. Sub-Graphs (NeuralPathways)
    # Exclude self to prevent recursion!
    pathways = NeuralPathway.objects.exclude(id=pathway.id).values('id', 'name')

    for p in pathways:
        p['category'] = 'Sub-Graphs'
        p['is_book'] = True

    # Combine
    return JsonResponse({KEY_LIBRARY: effectors + list(pathways)})


def get_neuron_details(
    pathway: NeuralPathway, request: HttpRequest
) -> JsonResponse:
    neuron_id = request.GET.get('neuron_id')
    neuron = get_object_or_404(Neuron, id=neuron_id, pathway=pathway)

    # 1. Inspect the Effector to find variables
    # We look at all arguments and switches
    variables = set()

    if neuron.effector:
        # Check Args
        args = neuron.effector.effectorargumentassignment_set.all()
        for a in args:
            raw = a.argument.argument
            found = re.findall(r'\{\{\s*(\w+)\s*\}\}', raw)
            variables.update(found)

        # Check Switches
        switches = neuron.effector.switches.all()
        for s in switches:
            raw = s.flag + (s.value or '')
            found = re.findall(r'\{\{\s*(\w+)\s*\}\}', raw)
            variables.update(found)

        # Check Executable Args (Base args)
        exe_args = neuron.effector.executable.executableargumentassignment_set.all()
        for a in exe_args:
            raw = a.argument.argument
            found = re.findall(r'\{\{\s*(\w+)\s*\}\}', raw)
            variables.update(found)

    # 2. Get Global Context (Blue)
    # We use the pathway's environment
    global_context = VariableRenderer.extract_variables(pathway.environment)

    # 3. Get Overrides (Yellow)
    from .models import NeuronContext

    overrides = {c.key: c.value for c in neuron.neuroncontext_set.all()}

    variables.update(overrides.keys())

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
            item['is_readonly'] = True

        matrix.append(item)

    return JsonResponse(
        {
            'neuron_id': neuron.id,
            'name': neuron.effector.name if neuron.effector else 'Unknown',
            'description': neuron.effector.description
            if neuron.effector
            else '',
            'distribution_mode_id': neuron.distribution_mode_id,
            'context_matrix': matrix,
            'effector_id': neuron.effector_id,
            'invoked_pathway_id': neuron.invoked_pathway_id,
        }
    )


def handle_save_neuron_context(
    pathway: NeuralPathway, payload: dict
) -> JsonResponse:
    neuron_id = payload.get('neuron_id')
    updates = payload.get('updates', [])  # List of {key, value}

    neuron = get_object_or_404(Neuron, id=neuron_id, pathway=pathway)

    from .models import NeuronContext

    for update in updates:
        key = update.get('key')
        value = update.get('value')

        if not key:
            continue

        if not value:
            # Remove override if empty
            NeuronContext.objects.filter(neuron=neuron, key=key).delete()
        else:
            NeuronContext.objects.update_or_create(
                neuron=neuron, key=key, defaults={'value': value}
            )

    # Also handle distribution mode update
    dist_mode = payload.get('distribution_mode_id')
    if dist_mode:
        neuron.distribution_mode_id = dist_mode
        neuron.save(update_fields=['distribution_mode'])

    return JsonResponse({'status': 'saved'})


def get_neuron_telemetry(
    pathway: NeuralPathway, request: HttpRequest
) -> JsonResponse:
    neuron_id = request.GET.get('neuron_id')
    spike_train_id = request.GET.get('spike_train_id')

    if not spike_train_id:
        return JsonResponse({'error': 'No spike_train_id'}, status=400)

    spike = (
        Spike.objects.filter(spike_train_id=spike_train_id, neuron_id=neuron_id)
        .order_by('-created')
        .first()
    )

    if not spike:
        return JsonResponse({'status': 'pending', 'logs': ''})

    # --- 1. LOGS ---
    logs = spike.application_log or ''
    log_lines = logs.split('\n')
    effector_tail = log_lines[-20:] if len(log_lines) > 20 else log_lines

    exec_logs = spike.execution_log or ''
    exec_lines = exec_logs.split('\n')
    exec_tail = exec_lines[-20:] if len(exec_lines) > 20 else exec_lines

    # --- 2. COMMAND ---
    command = 'Command not captured.'
    if spike.execution_log and 'Command:' in spike.execution_log:
        pass

    if spike.effector:
        try:
            neuron = Neuron.objects.get(id=neuron_id)
            from .models import NeuronContext

            overrides = {c.key: c.value for c in neuron.neuroncontext_set.all()}

            cmd_list = spike.effector.get_full_command(
                environment=pathway.environment, extra_context=overrides
            )
            command = ' '.join(cmd_list)
        except Exception as e:
            command = f'Error interpreting command: {e}'

    # --- 3. CONTEXT PARAMETERS ---
    variables = set()
    if spike.effector:
        for a in spike.effector.effectorargumentassignment_set.all():
            found = re.findall(r'\{\{\s*(\w+)\s*\}\}', a.argument.argument)
            variables.update(found)
        for s in spike.effector.switches.all():
            found = re.findall(r'\{\{\s*(\w+)\s*\}\}', s.flag + (s.value or ''))
            variables.update(found)
        for a in spike.effector.executable.executableargumentassignment_set.all():
            found = re.findall(r'\{\{\s*(\w+)\s*\}\}', a.argument.argument)
            variables.update(found)

    global_context = VariableRenderer.extract_variables(pathway.environment)

    overrides = {}
    if spike.neuron:
        from .models import NeuronContext

        overrides = {
            c.key: c.value for c in spike.neuron.neuroncontext_set.all()
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

    return JsonResponse(
        {
            'status_name': spike.status.name,
            'status_id': spike.status_id,
            'agent': str(spike.target) if spike.target else 'Pending...',
            'result_code': spike.result_code,
            'logs': '\n'.join(effector_tail),
            'exec_logs': '\n'.join(exec_tail),
            'command': command,
            'context_matrix': matrix,
            'spike_id': str(spike.id),
            'duration': '0s',
        }
    )


def get_execution_status(
    pathway: NeuralPathway, spike_train_id: uuid.UUID = None
) -> JsonResponse:
    """Returns the current state of the graph and the overall spike_train status."""
    if not spike_train_id:
        return JsonResponse({KEY_STATUS: STATUS_READY})

    try:
        spike_train = SpikeTrain.objects.select_related('status').get(
            id=spike_train_id
        )

        neuron_status_map = {}
        for spike in spike_train.spikes.all().order_by('created'):
            if spike.neuron_id:
                spike_data = {
                    'status_id': spike.status_id,
                    'spike_id': str(spike.id),
                }
                child = spike.child_trains.first()
                if child:
                    spike_data['child_spike_train_id'] = str(child.id)
                neuron_status_map[str(spike.neuron_id)] = spike_data

        return JsonResponse(
            {KEY_STATUS: spike_train.status.name, 'neurons': neuron_status_map}
        )
    except SpikeTrain.DoesNotExist:
        return JsonResponse(
            {KEY_STATUS: STATUS_ERROR, MESSAGE: 'SpikeTrain not found'}
        )
    except Exception as e:
        logger.exception('Status Check Failed')
        return JsonResponse({KEY_STATUS: STATUS_ERROR, MESSAGE: str(e)})


class CNSGraphLaunchAPI(View):
    def post(self, request, pathway_id):
        try:
            controller = CNS(pathway_id=pathway_id)
            controller.start()
            return JsonResponse(
                {
                    ACTION_STATUS: STATUS_STARTED,
                    SPIKE_TRAIN_ID: str(controller.spike_train.id),
                }
            )
        except Exception as e:
            logger.exception('[CNS] Graph Launch Failed')
            return JsonResponse(
                {ACTION_STATUS: STATUS_ERROR, MESSAGE: str(e)},
                status=ERROR_STATUS_CODE,
            )


class CNSGraphSpikeTrainStatusAPI(View):
    def get(self, request, spike_train_id):
        spike_train = get_object_or_404(SpikeTrain, id=spike_train_id)

        spikes = spike_train.spikes.all().order_by('created')
        neuron_status_map = {}

        # Special Case: Begin Play Neuron (always green once spike_train exists)
        begin_play_neuron = spike_train.pathway.neurons.filter(
            effector_id=Effector.BEGIN_PLAY
        ).first()
        if begin_play_neuron:
            neuron_status_map[str(begin_play_neuron.id)] = {
                'status_id': CNSStatusID.SUCCESS,
                'spike_id': None,
            }

        for spike in spikes:
            if spike.neuron_id:
                neuron_status_map[str(spike.neuron_id)] = {
                    'status_id': spike.status_id,
                    'spike_id': str(spike.id),
                }

        return JsonResponse(
            {
                'status_label': spike_train.status.name,
                'is_active': spike_train.is_active,
                'neurons': neuron_status_map,
            }
        )
