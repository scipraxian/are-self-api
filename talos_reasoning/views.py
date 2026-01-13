# [file: talos_reasoning/views.py]
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, View

from .engine import ReasoningEngine
from .models import ReasoningSession, ReasoningStatusID


class CortexSessionView(DetailView):
    """
    Mission Control for a Reasoning Session.
    """
    model = ReasoningSession
    template_name = "talos_reasoning/cortex_view.html"
    context_object_name = "session"
    pk_url_kwarg = 'session_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.get_object()

        # 1. Active Data
        context['turns'] = session.turns.all().prefetch_related(
            'tool_calls', 'tool_calls__tool').order_by('turn_number')
        context['goals'] = session.goals.all().order_by('created')
        context['engrams'] = session.engrams.all().order_by('-relevance_score')

        # 2. History Data (Previous Sessions)
        # Exclude current, order by newest
        context['history_sessions'] = ReasoningSession.objects.exclude(
            id=session.id
        ).order_by('-modified')[:20]

        return context


class CortexStreamPartialView(View):
    """
    Returns the partial HTML for the turn stream (for HTMX polling).
    """

    def get(self, request, session_id):
        session = get_object_or_404(ReasoningSession, id=session_id)
        turns = session.turns.all().prefetch_related(
            'tool_calls', 'tool_calls__tool').order_by('turn_number')

        return render(request, "talos_reasoning/partials/cognitive_stream.html",
                      {
                          'session': session,
                          'turns': turns,
                      })


class CortexTickActionView(View):
    """
    Triggers a manual tick of the Reasoning Engine.
    """

    def post(self, request, session_id):
        engine = ReasoningEngine()
        engine.tick(session_id)

        # Return the updated stream
        session = get_object_or_404(ReasoningSession, id=session_id)
        turns = session.turns.all().prefetch_related(
            'tool_calls', 'tool_calls__tool').order_by('turn_number')

        return render(request, "talos_reasoning/partials/cognitive_stream.html",
                      {
                          'session': session,
                          'turns': turns,
                      })


class CortexLaunchView(View):
    """
    Launches the Manual Cortex.
    REUSE LOGIC: Finds the most recent 'Manual' session (no spawn link).
    """

    def get(self, request):
        # 1. Look for existing manual session
        session = ReasoningSession.objects.filter(
            spawn_link__isnull=True
        ).order_by('-created').first()

        if session:
            # Wake it up if it was sleeping/completed
            if session.status_id in [ReasoningStatusID.COMPLETED, ReasoningStatusID.MAXED_OUT, ReasoningStatusID.ERROR]:
                session.status_id = ReasoningStatusID.ACTIVE
                session.save()
        else:
            # 2. Only create if none exists
            session = ReasoningSession.objects.create(
                goal="Manual Investigation (User Initiated)",
                status_id=ReasoningStatusID.ACTIVE,
                max_turns=20
            )

        return redirect('talos_reasoning:cortex_view', session_id=session.id)