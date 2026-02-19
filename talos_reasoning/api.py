from django.shortcuts import get_object_or_404, render
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
    turns = (
        session.turns.all()
        .prefetch_related('tool_calls', 'tool_calls__tool')
        .order_by('turn_number')
    )

    # 3. Memory: Engrams (Hippocampus Link)
    # Fetch engrams linked specifically to this session
    engrams = session.talosengram_set.filter(is_active=True).order_by(
        '-relevance_score', '-created'
    )

    context = {
        'session': session,
        'goals': goals,
        'turns': turns,
        'engrams': engrams,
        'is_active': session.status_id
        in [ReasoningStatusID.ACTIVE, ReasoningStatusID.PENDING],
    }

    # HTMX Partial: Just update the stream
    if (
        request.headers.get('HX-Request')
        and request.GET.get('partial') == 'stream'
    ):
        return render(
            request,
            'talos_reasoning/partials/cortex_stream_partial.html',
            context,
        )

    return render(
        request, 'talos_reasoning/talos_reasoning_window.html', context
    )
