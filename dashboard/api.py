import logging
import os
import threading
import time
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from central_nervous_system.models import NeuralPathway, SpikeTrain
from central_nervous_system.serializers.serializers import (
    CNSNeuralPathwaySerializer,
    CNSSwimlaneSerializer,
)
from config.celery import app as celery_app
from environments.models import ProjectEnvironment
from environments.serializers import ProjectEnvironmentSerializer

logger = logging.getLogger(__name__)


def delayed_shutdown():
    """Background thread to kill the Daphne/Django process after returning the HTTP response."""
    time.sleep(1.0)
    os._exit(0)


class DashboardViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    @action(detail=False, methods=['get'])
    def summary(self, request):
        client_sync_str = request.query_params.get('last_sync')
        client_sync_time = (
            parse_datetime(client_sync_str) if client_sync_str else None
        )

        include_static = request.query_params.get('static', 'true') == 'true'
        is_first_load = include_static

        # Always stamp the exact moment the request started
        now = timezone.now()
        response_data = {'server_time': now.isoformat()}

        if is_first_load:
            envs = ProjectEnvironment.objects.all().order_by('name')
            response_data['environments'] = ProjectEnvironmentSerializer(
                envs, many=True
            ).data

            books = (
                NeuralPathway.objects.all()
                .prefetch_related('tags')
                .order_by('name')
            )
            response_data['pathways'] = CNSNeuralPathwaySerializer(
                books, many=True
            ).data

        root_spawns = SpikeTrain.objects.filter(
            parent_spike__isnull=True, environment__selected=True
        )

        if not is_first_load and client_sync_time:
            safe_sync_time = client_sync_time - timedelta(seconds=2.5)
            has_changes = (
                SpikeTrain.objects.filter(environment__selected=True)
                .filter(
                    Q(modified__gt=safe_sync_time)
                    | Q(spikes__modified__gt=safe_sync_time)
                )
                .exists()
            )
            if not has_changes:
                return Response(status=status.HTTP_204_NO_CONTENT)

        root_spawns = (
            root_spawns.select_related('status', 'pathway', 'environment')
            .prefetch_related('spikes', 'spikes__status', 'spikes__effector')
            .order_by('-created')[:20]
        )

        # Force query evaluation
        spawns_list = reversed(list(root_spawns))

        # If nothing changed in the overlapping window, halt DOM patching
        if not is_first_load and client_sync_time and not spawns_list:
            return Response(status=status.HTTP_204_NO_CONTENT)

        response_data['recent_missions'] = CNSSwimlaneSerializer(
            spawns_list, many=True
        ).data
        return Response(response_data)

    @action(detail=False, methods=['post'])
    def shutdown(self, request):
        """Triggers a systemic shutdown of Celery workers and the ASGI server.

        DEPRECATED: Use /api/v2/system-control/shutdown/ instead.
        """
        logger.warning(
            '[Dashboard] Using deprecated shutdown endpoint. Use '
            '/api/v2/system-control/shutdown/ instead.'
        )
        # 1. Send shutdown broadcast to Celery workers
        celery_app.control.shutdown()

        # 2. SpikeTrain a delayed thread to kill the Django process
        threading.Thread(target=delayed_shutdown).start()

        return Response(
            {'status': 'System shutdown initiated'}, status=status.HTTP_200_OK
        )
