import os
import threading
import time

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.celery import app as celery_app
from environments.models import ProjectEnvironment
from environments.serializers import ProjectEnvironmentSerializer
from hydra.models import HydraSpawn, HydraSpellbook
from hydra.serializers import HydraSpawnSerializer, HydraSpellbookSerializer


class DashboardViewSet(viewsets.ViewSet):
    """
    System-level operations and data aggregation for the Talos Command Center.
    """

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Aggregates the data needed for the main mission control dashboard."""
        envs = ProjectEnvironment.objects.all().order_by('name')
        env_data = ProjectEnvironmentSerializer(envs, many=True).data

        books = (
            HydraSpellbook.objects.all()
            .prefetch_related('tags')
            .order_by('name')
        )
        book_data = HydraSpellbookSerializer(books, many=True).data

        root_spawns = (
            HydraSpawn.objects.filter(
                parent_head__isnull=True, environment__selected=True
            )
            .select_related('status', 'spellbook', 'environment')
            .prefetch_related('heads', 'heads__status', 'heads__spell')
            .order_by('-created')[:20]
        )

        spawn_data = HydraSpawnSerializer(root_spawns, many=True).data

        return Response(
            {
                'environments': env_data,
                'spellbooks': book_data,
                'recent_missions': spawn_data,
            }
        )

    @action(detail=False, methods=['post'])
    def shutdown(self, request):
        """Initiates a system-wide shutdown."""
        try:
            celery_app.control.shutdown()
        except Exception:
            pass

        def kill_server():
            time.sleep(1)
            os._exit(0)

        threading.Thread(target=kill_server, daemon=True).start()

        return Response({'status': 'System Offline Initiated'})
