from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from talos_reasoning import serializers
from talos_reasoning.models import ReasoningSession, ReasoningStatusID


@require_http_methods(['GET'])
def reasoning_interface(request, session_id):
    """
    The Standalone Cortex 'Situation Room'.
    Aggregates Strategy (Goals), Tactics (Turns), and Memory (Engrams).
    """
    session = get_object_or_404(ReasoningSession, id=session_id)

    # 1. Strategy: Goals
    goals = session.goals.all().order_by('created')

    # 2. Tactics: The Cognitive Stream
    turns = (session.turns.all().prefetch_related(
        'tool_calls', 'tool_calls__tool').order_by('turn_number'))

    # 3. Memory: Engrams (Hippocampus Link)
    # Fetch engrams linked specifically to this session
    engrams = session.engram.filter(is_active=True).order_by(
        '-relevance_score', '-created')

    context = {
        'session':
            session,
        'goals':
            goals,
        'turns':
            turns,
        'engrams':
            engrams,
        'is_active':
            session.status_id in
            [ReasoningStatusID.ACTIVE, ReasoningStatusID.PENDING],
    }

    # HTMX Partial: Just update the stream
    if (request.headers.get('HX-Request') and
            request.GET.get('partial') == 'stream'):
        return render(
            request,
            'talos_reasoning/partials/cortex_stream_partial.html',
            context,
        )

    return render(request, 'talos_reasoning/talos_reasoning_window.html',
                  context)


@require_http_methods(['GET'])
def lcars_view(request, session_id):
    """
    Renders the futuristic LCARS interface for a reasoning session.
    """
    session = get_object_or_404(ReasoningSession, id=session_id)
    context = {
        'session': session,
    }
    return render(request, 'talos_reasoning/lcars_view.html', context)


@require_http_methods(['GET'])
def session_graph_data_api(request, session_id):
    """
    Returns JSON data for the session graph visualization.
    Nodes: Turns, Engrams
    Edges: Turn -> Engram (creation/reference)
    """
    session = get_object_or_404(ReasoningSession, id=session_id)

    # Fetch data
    turns = (session.turns.all().order_by('turn_number').prefetch_related(
        'tool_calls', 'tool_calls__tool'))
    engrams = session.engram.all()

    # CONSTANTS
    TYPE_TURN = 'turn'
    TYPE_TOOL = 'tool'
    TYPE_ENGRAM = 'engram'
    LINK_SEQUENCE = 'sequence'
    LINK_USES_TOOL = 'uses_tool'
    LINK_CREATED_IN = 'created_in'

    nodes = []
    links = []

    # Track unique tools to avoid duplicates in the graph
    # Key: tool_name, Value: node_id
    tool_map = {}

    # Serialize Data
    turn_data = serializers.ReasoningTurnSerializer(turns, many=True).data
    # We still use objects for Engrams to easily access the source_turns relation
    # without adding complex read-only fields to the serializer for now.

    # Process Turns
    for i, turn in enumerate(turn_data):
        turn_id = turn['id']
        node_id = f'{TYPE_TURN}-{turn_id}'

        nodes.append({
            'id': node_id,
            'type': TYPE_TURN,
            'label': f"Turn {turn['turn_number']}",
            # Flatten for frontend
            'turn_number': turn['turn_number'],
            'status': turn['status_name'],
            'thought_process': turn['thought_process'],
            'timestamp': turn['created'],
        })

        # Link sequential turns
        if i > 0:
            prev_turn_id = turn_data[i - 1]['id']
            links.append({
                'source': f'{TYPE_TURN}-{prev_turn_id}',
                'target': node_id,
                'type': LINK_SEQUENCE
            })

        # Process Tool Calls
        # turn['tool_calls'] is a list of dicts from the serializer
        for call in turn['tool_calls']:
            tool_name = call['tool_name']
            tool_node_id = f'{TYPE_TOOL}-{tool_name}'

            # Create Tool Node if not exists
            if tool_name not in tool_map:
                tool_map[tool_name] = tool_node_id
                nodes.append({
                    'id': tool_node_id,
                    'type': TYPE_TOOL,
                    'label': tool_name,
                    'is_async': call['tool_is_async'],
                })

            # Link Turn -> Tool
            links.append({
                'source': node_id,
                'target': tool_node_id,
                'type': LINK_USES_TOOL,
                'call_id': call['call_id'],
                'arguments': call['arguments'],
                'result': call['result_payload'] or ''
            })

    # Add Engrams as nodes
    for engram in engrams:
        node_id = f'{TYPE_ENGRAM}-{engram.id}'
        # Use Serializer for the dict representation to ensure consistency
        serialized_engram = serializers.TalosEngramSerializer(engram).data

        nodes.append({
            'id': node_id,
            'type': TYPE_ENGRAM,
            'label': f'Engram #{engram.id}',
            'description': serialized_engram['description'],
            'relevance': serialized_engram['relevance_score'],
            'is_active': serialized_engram['is_active'],
        })

        # Link Engram to Source Turns
        for turn in engram.source_turns.all():
            links.append({
                'source': f'{TYPE_TURN}-{turn.id}',
                'target': node_id,
                'type': LINK_CREATED_IN,
            })

    data = {
        'nodes': nodes,
        'links': links,
        'session': serializers.ReasoningSessionSerializer(session).data
    }

    return JsonResponse(data)
