"""System-wide API endpoints (Config)."""

from rest_framework.response import Response
from rest_framework.views import APIView

from frontal_lobe.models import ReasoningSession
from hypothalamus.models import AIModel
from identity.models import IdentityDisc


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
