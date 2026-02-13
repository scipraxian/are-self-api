from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from environments.models import ProjectEnvironment
from environments.serializers import ProjectEnvironmentSerializer
from hydra.models import HydraHead, HydraSpawn, HydraSpellbook
from hydra.serializers import (
    HydraSpellbookSerializer,
    HydraSwimlaneSerializer,
)


class DashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def summary(self, request):
        client_sync_str = request.query_params.get('last_sync')

        # 1. Fast path: Check if anything changed
        if client_sync_str:
            client_sync_time = parse_datetime(client_sync_str)
            if client_sync_time:
                latest_spawn = (
                    HydraSpawn.objects.order_by('-modified')
                    .values_list('modified', flat=True)
                    .first()
                )
                latest_head = (
                    HydraHead.objects.order_by('-modified')
                    .values_list('modified', flat=True)
                    .first()
                )

                last_mod = max(
                    filter(None, [latest_spawn, latest_head]), default=None
                )

                if last_mod and last_mod <= client_sync_time:
                    return Response(status=status.HTTP_204_NO_CONTENT)

        # 2. Heavy logic proceeds only if data is stale
        include_static = request.query_params.get('static', 'true') == 'true'
        response_data = {'server_time': timezone.now().isoformat()}

        if include_static:
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

        root_spawns = (
            HydraSpawn.objects.filter(
                parent_head__isnull=True, environment__selected=True
            )
            .select_related('status', 'spellbook', 'environment')
            .prefetch_related('heads', 'heads__status', 'heads__spell')
            .order_by('-created')[:20]
        )

        response_data['recent_missions'] = HydraSwimlaneSerializer(
            root_spawns, many=True
        ).data
        return Response(response_data)