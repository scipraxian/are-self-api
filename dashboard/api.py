from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from environments.models import ProjectEnvironment
from environments.serializers import ProjectEnvironmentSerializer
from hydra.models import HydraSpawn, HydraSpellbook
from hydra.serializers import HydraSpellbookSerializer, HydraSwimlaneSerializer


class DashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def summary(self, request):
        client_sync_str = request.query_params.get('last_sync')
        client_sync_time = (
            parse_datetime(client_sync_str) if client_sync_str else None
        )

        include_static = request.query_params.get('static', 'true') == 'true'
        is_first_load = include_static

        # Always send the current time down for the NEXT poll
        response_data = {'server_time': timezone.now().isoformat()}

        if is_first_load:
            envs = ProjectEnvironment.objects.all().order_by('name')
            response_data['environments'] = ProjectEnvironmentSerializer(
                envs, many=True
            ).data

            books = (
                HydraSpellbook.objects.all()
                .prefetch_related('tags')
                .order_by('name')
            )
            response_data['spellbooks'] = HydraSpellbookSerializer(
                books, many=True
            ).data

        root_spawns = HydraSpawn.objects.filter(
            parent_head__isnull=True, environment__selected=True
        )

        # --- THE FIX: SAFETY BUFFER ---
        if not is_first_load and client_sync_time:
            # Subtract 2 seconds to catch overlapping DB transactions
            # where the Python clock was slightly ahead of the Celery commit.
            safe_sync_time = client_sync_time - timedelta(seconds=2)

            root_spawns = root_spawns.filter(
                Q(modified__gt=safe_sync_time)
                | Q(heads__modified__gt=safe_sync_time)
            ).distinct()

        root_spawns = (
            root_spawns.select_related('status', 'spellbook', 'environment')
            .prefetch_related('heads', 'heads__status', 'heads__spell')
            .order_by('-created')[:20]
        )

        missions_data = HydraSwimlaneSerializer(root_spawns, many=True).data

        # If our safety window caught NO changes, THEN return 204 to halt the UI loop
        if not is_first_load and client_sync_time and len(missions_data) == 0:
            return Response(status=status.HTTP_204_NO_CONTENT)

        response_data['recent_missions'] = missions_data
        return Response(response_data)
