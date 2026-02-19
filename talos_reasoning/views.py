# talos_reasoning/views.py
from dataclasses import asdict

from django.views.generic import DetailView

from .models import ReasoningSession, ReasoningStatusID
from .serializers import CortexContextDTO


class ReasoningInterfaceView(DetailView):
    """
    The Standalone Cortex 'Situation Room'.
    Aggregates Strategy (Goals), Tactics (Turns), and Memory (Engrams).
    """

    model = ReasoningSession
    pk_url_kwarg = 'session_id'
    context_object_name = 'session'

    def get_template_names(self):
        # HTMX Partial: Just update the stream
        if (
            self.request.headers.get('HX-Request')
            and self.request.GET.get('partial') == 'stream'
        ):
            return ['talos_reasoning/partials/cortex_stream_partial.html']
        return ['talos_reasoning/talos_reasoning_window.html']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object

        # 1. Build the strongly-typed DTO
        context_dto = CortexContextDTO(
            session=session,
            goals=session.goals.all().order_by('created'),
            turns=session.turns.all()
            .prefetch_related('tool_calls', 'tool_calls__tool')
            .order_by('turn_number'),
            engrams=session.engram.filter(is_active=True).order_by(
                '-relevance_score', '-created'
            ),
            is_active=session.status_id
            in [ReasoningStatusID.ACTIVE, ReasoningStatusID.PENDING],
        )

        # 2. Safely unpack it into Django's context dictionary
        context.update(asdict(context_dto))
        return context


class LcarsView(DetailView):
    """Renders the futuristic LCARS interface wrapper."""

    model = ReasoningSession
    pk_url_kwarg = 'session_id'
    context_object_name = 'session'
    template_name = 'talos_reasoning/lcars_view.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch the last 15 sessions excluding the current one
        context['history_sessions'] = ReasoningSession.objects.exclude(
            id=self.object.id
        ).order_by('-created')[:15]
        return context
