from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

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
    turns = session.turns.all().order_by('turn_number').prefetch_related(
        'tool_calls', 'tool_calls__tool')
    engrams = session.engram.all()

    nodes = []
    links = []

    # Track unique tools to avoid duplicates in the graph
    # Key: tool_name, Value: node_id
    tool_map = {}

    # Add Turns as nodes
    for turn in turns:
        nodes.append({
            'id': f'turn-{turn.id}',
            'type': 'turn',
            'label': f'Turn {turn.turn_number}',
            'turn_number': turn.turn_number,
            'status': turn.status.name,
            'thought_process': turn.thought_process,
            'timestamp': turn.created.isoformat(),
        })

        # Link sequential turns
        if turn.turn_number > 1:
            prev_turn = turns.filter(turn_number=turn.turn_number - 1).first()
            if prev_turn:
                links.append({
                    'source': f'turn-{prev_turn.id}',
                    'target': f'turn-{turn.id}',
                    'type': 'sequence'
                })

        # Process Tool Calls for this turn
        for call in turn.tool_calls.all():
            tool_name = call.tool.name
            tool_node_id = f'tool-{tool_name}'

            # Create Tool Node if not exists
            if tool_name not in tool_map:
                tool_map[tool_name] = tool_node_id
                nodes.append({
                    'id': tool_node_id,
                    'type': 'tool',
                    'label': tool_name,
                    'is_async': call.tool.is_async,
                })

            # Link Turn -> Tool
            links.append({
                'source': f'turn-{turn.id}',
                'target': tool_node_id,
                'type': 'uses_tool',
                'call_id': call.call_id,
                'arguments': call.arguments,
                'result': call.result_payload
            })

    # Add Engrams as nodes
    for engram in engrams:
        nodes.append({
            'id': f'engram-{engram.id}',
            'type': 'engram',
            'label': f'Engram #{engram.id}',
            'description': engram.description,
            'relevance': engram.relevance_score,
            'is_active': engram.is_active,
        })

        # Link Engram to Source Turns
        for turn in engram.source_turns.all():
            links.append({
                'source': f'turn-{turn.id}',
                'target': f'engram-{engram.id}',
                'type': 'created_in'
            })

    data = {
        'nodes': nodes,
        'links': links,
        'session': {
            'id': str(session.id),
            'goal': session.goal,
            'status': session.status.name
        }
    }

    return JsonResponse(data)
