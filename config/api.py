"""System-wide API endpoints (Config)."""

from django.db.models import Count
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from rest_framework.response import Response
from rest_framework.views import APIView

from frontal_lobe.models import ReasoningSession
from hypothalamus.models import AIModel
from identity.models import IdentityDisc


@require_GET
def health_probe(request):
    """Frontend disconnect-overlay probe.

    Plain Django view — no DB query, no auth — so the frontend can poll
    it cheaply during install / uninstall / move-to-genome restarts and
    flip the overlay off the instant the worker is reachable again.
    """
    return JsonResponse({'status': 'ok'})


class StatsAPIView(APIView):
    """Return lightweight system statistics — model counts only."""

    def get(self, request):
        """Return counts for identity-discs, ai-models, reasoning-sessions.

        Uses single-query counts, not full object fetches.
        """
        return Response({
            'identity_disc_count': IdentityDisc.objects.count(),
            'ai_model_count': AIModel.objects.count(),
            'reasoning_session_count': ReasoningSession.objects.count(),
        })


class LatestSpikesAPIView(APIView):
    """Lightweight latest spikes for the dashboard. Excludes Begin Play."""

    def get(self, request):
        from central_nervous_system.models import Spike
        from central_nervous_system.serializers_v2 import (
            SpikeMinimalSerializer,
        )

        qs = (
            Spike.objects.select_related('status', 'effector')
            .exclude(effector__name='Begin Play')
            .order_by('-created')[:10]
        )
        return Response(SpikeMinimalSerializer(qs, many=True).data)


class LatestSessionsAPIView(APIView):
    """Lightweight latest sessions for the dashboard."""

    def get(self, request):
        from frontal_lobe.serializers import ReasoningSessionMinimalSerializer

        qs = (
            ReasoningSession.objects.select_related('status', 'identity_disc')
            .annotate(turns_count=Count('turns'))
            .order_by('-modified')[:10]
        )
        return Response(ReasoningSessionMinimalSerializer(qs, many=True).data)
