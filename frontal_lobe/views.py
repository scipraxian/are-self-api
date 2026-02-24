from django.views.generic import DetailView

from .models import ReasoningSession, ReasoningStatusID
from .serializers import ReasoningSessionSerializer


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
            return ['frontal_lobe/partials/cortex_stream_partial.html']
        return ['frontal_lobe/frontal_lobe_window.html']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object

        # 1. Let the DRF Serializer do the heavy lifting!
        serialized_data = ReasoningSessionSerializer(session).data

        # 2. Unpack the deeply nested JSON tree directly into the template context
        context.update(serialized_data)

        # 3. Add the UI helper flag
        context['is_active'] = session.status_id in [
            ReasoningStatusID.ACTIVE,
            ReasoningStatusID.PENDING,
        ]

        return context


class LcarsView(DetailView):
    """Renders the futuristic LCARS interface wrapper."""

    model = ReasoningSession
    pk_url_kwarg = 'session_id'
    context_object_name = 'session'
    template_name = 'frontal_lobe/lcars_view.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch the last 15 sessions excluding the current one
        context['history_sessions'] = ReasoningSession.objects.exclude(
            id=self.object.id
        ).order_by('-created')[:15]
        return context
