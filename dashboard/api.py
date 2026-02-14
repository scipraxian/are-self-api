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

        # Always stamp the exact moment the request started
        now = timezone.now()
        response_data = {'server_time': now.isoformat()}

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

        if not is_first_load and client_sync_time:
            # MVCC Race Condition Protection: Roll back the clock 2.5 seconds.
            # This ensures we catch any Celery transactions that were assigned
            # a timestamp slightly in the past, but committed AFTER our last poll.
            safe_sync_time = client_sync_time - timedelta(seconds=2.5)
            root_spawns = root_spawns.filter(
                Q(modified__gt=safe_sync_time)
                | Q(heads__modified__gt=safe_sync_time)
            ).distinct()

        root_spawns = (
            root_spawns.select_related('status', 'spellbook', 'environment')
            .prefetch_related('heads', 'heads__status', 'heads__spell')
            .order_by('-created')[:20]
        )

        # Force query evaluation
        spawns_list = reversed(list(root_spawns))

        # If nothing changed in the overlapping window, halt DOM patching
        if not is_first_load and client_sync_time and not spawns_list:
            return Response(status=status.HTTP_204_NO_CONTENT)

        response_data['recent_missions'] = HydraSwimlaneSerializer(
            spawns_list, many=True
        ).data
        return Response(response_data)
